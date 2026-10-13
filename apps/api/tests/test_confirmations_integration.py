import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from local_shop.db import build_engine
from local_shop.models import ConfirmationRevision, Reservation
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_cancellations_integration import cancel
from test_catalog_integration import category, product
from test_customers_integration import A, B, base, create, headers
from test_customers_integration import client as client

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)


def propose(client, row, alias="merchant-a", tenant=A, key=None, **extra):
    return client.post(
        base(tenant) + f"/reservations/{row['id']}/confirmation-revisions",
        headers=headers(client, alias, key),
        json={
            "expected_version": row["version"],
            "summary": "确认候选：半斤分两袋",
            "items": [{"name": "合成商品", "quantity": "0.5", "unit": "斤", "spec": "分两袋"}],
            "fulfillment_at": "2026-10-15T17:00:00+08:00",
            "time_note": "已约定具体日期",
            "change_reason": "商户整理沟通内容，需要重新确认",
            **extra,
        },
    )


def move(client, row, target="CONFIRMED", key=None, **extra):
    return client.post(
        base() + f"/reservations/{row['id']}/transitions",
        headers=headers(client, "merchant-a", key),
        json={
            "expected_version": row["version"],
            "target_status": target,
            **extra,
        },
    )


def acknowledge(client, row, **extra):
    return move(
        client,
        row,
        confirmation_revision_id=row["confirmation_revisions"][-1]["id"],
        customer_agreed=True,
        **extra,
    )


def test_revision_keeps_original_text_quantity_time_and_requires_explicit_confirmation(client):
    original = create(
        client,
        items=[{"name": "原始物品", "quantity": "1.25", "unit": "盒"}],
        expected_at="2026-10-15T10:00:00+08:00",
    ).json()
    pending = propose(client, original).json()
    assert pending["raw_text"] == original["raw_text"]
    assert (
        pending["items"] == original["items"] and pending["expected_at"] == original["expected_at"]
    )
    revision = pending["confirmation_revisions"][0]
    assert revision["details"]["items"][0]["quantity"] == "0.5"
    assert revision["details"]["items"][0]["unit"] == "斤"
    assert revision["confirmed_version"] is None and pending["status"] == "PENDING_CONFIRMATION"
    assert move(client, pending).json()["code"] == "EXPLICIT_RECONFIRMATION_REQUIRED"
    assert move(client, pending, "PREPARING").status_code == 409
    assert move(client, pending, confirmation_revision_id=revision["id"]).status_code == 409
    assert (
        move(
            client, pending, confirmation_revision_id=str(uuid4()), customer_agreed=True
        ).status_code
        == 409
    )
    confirmed = acknowledge(client, pending).json()
    assert confirmed["status"] == "CONFIRMED" and confirmed["version"] == 3
    assert confirmed["confirmation_revisions"][0]["confirmed_version"] == 3
    assert confirmed["confirmation_revisions"][0]["agreement_recorded_by"] == "MERCHANT"
    assert move(client, confirmed, "PREPARING").status_code == 200


def test_new_revision_resets_confirmation_without_rewriting_older_revision(client):
    original = create(client).json()
    first = acknowledge(client, propose(client, original).json()).json()
    previous_revision = first["confirmation_revisions"][0]
    latest = propose(client, first, summary="改成另一个备货结果").json()
    assert latest["status"] == "PENDING_CONFIRMATION"
    assert latest["confirmation_revisions"][0] == previous_revision
    assert move(client, latest, "PREPARING").status_code == 409
    assert (
        move(
            client, latest, confirmation_revision_id=previous_revision["id"], customer_agreed=True
        ).status_code
        == 409
    )
    final = acknowledge(client, latest).json()
    assert len(final["confirmation_revisions"]) == 2
    assert final["raw_text"] == original["raw_text"]
    mine = client.get(
        "/api/v1/me/records/reservation/" + final["id"], headers=headers(client)
    ).json()
    assert mine["confirmation_revisions"] == final["confirmation_revisions"]
    assert not {"actor_id", "confirmed_by"} & mine["confirmation_revisions"][0].keys()


def test_confirmation_tenant_customer_and_product_boundaries(client):
    row = create(client).json()
    for alias, tenant in (("customer-a", A), ("merchant-b", B), ("merchant-b", A)):
        assert propose(client, row, alias=alias, tenant=tenant).status_code == 404
    other_cat = category(client, tenant=B, alias="merchant-b")
    prod = product(client, other_cat["id"], tenant=B, alias="merchant-b").json()
    assert (
        propose(
            client,
            row,
            items=[{"product_id": prod["id"], "name": "x", "quantity": "1", "unit": "盒"}],
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/me/records/reservation/" + row["id"], headers=headers(client, "customer-b")
        ).status_code
        == 404
    )


def test_revision_product_snapshot_cannot_be_forged_or_later_mutated(client):
    cat = category(client)
    prod = product(client, cat["id"], reference_price="3.50").json()
    row = propose(
        client,
        create(client).json(),
        items=[{"product_id": prod["id"], "name": "伪造", "quantity": "0.25", "unit": "假单位"}],
    ).json()
    snapshot = row["confirmation_revisions"][0]["details"]["items"][0]
    assert snapshot["name"] == prod["name"] and snapshot["unit"] == prod["unit"]
    assert snapshot["reference_price"] == "3.50"
    from test_catalog_integration import update_product

    assert update_product(client, prod, name="后来改名", status="ARCHIVED").status_code == 200
    stored = client.get(
        base() + "/reservations/" + row["id"], headers=headers(client, "merchant-a")
    ).json()
    assert stored["confirmation_revisions"][0]["details"]["items"][0] == snapshot


def test_confirmation_idempotency_and_concurrent_versions(client):
    row = create(client).json()
    key = str(uuid4())
    first = propose(client, row, key=key)
    assert first.status_code == 201
    assert propose(client, row, key=key).json() == first.json()
    assert propose(client, row, key=key, summary="changed").status_code == 409
    pending = first.json()
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: acknowledge(client, pending), range(5)))
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409]
    confirmed = next(r.json() for r in results if r.status_code == 200)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: propose(client, confirmed), range(5)))
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409, 409]


def test_preparation_and_cancellation_gate_block_detail_changes(client):
    row = move(client, create(client).json()).json()
    row = move(client, row, "PREPARING").json()
    assert propose(client, row).json()["code"] == "CONFIRMATION_CHANGE_NOT_ALLOWED"
    pending_cancel = cancel(client, create(client).json()).json()
    assert propose(client, pending_cancel).json()["code"] == "CANCELLATION_REVIEW_REQUIRED"


@pytest.mark.parametrize(
    "patch",
    [
        {"summary": "", "items": []},
        {"fulfillment_at": "2026-10-15T10:00:00"},
        {"change_reason": " "},
        {"items": [{"name": "x", "quantity": "0", "unit": "斤"}]},
        {"customer_user_id": "fake"},
        {"confirmed_version": 2},
    ],
    ids=["empty", "naive-time", "no-reason", "bad-quantity", "spoof-owner", "spoof-ack"],
)
def test_invalid_confirmation_input(client, patch):
    assert propose(client, create(client).json(), **patch).status_code == 422


def test_confirmation_commit_failure_rolls_back_revision_and_version(client, pg_settings):
    row = create(client).json()

    def fail(session):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        assert propose(client, row).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.get(Reservation, UUID(row["id"])).version == 1
        assert session.scalar(select(func.count()).select_from(ConfirmationRevision)) == 0
    engine.dispose()
    assert propose(client, row).status_code == 201
