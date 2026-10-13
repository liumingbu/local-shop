import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from local_shop.db import build_engine
from local_shop.models import CancellationRequest, RecordEvent, Reservation, Tenant
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from test_customers_integration import A, B, base, create, headers
from test_customers_integration import client as client

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)


def cancel(client, row, alias="customer-a", key=None, **extra):
    return client.post(
        f"/api/v1/me/reservations/{row['id']}/cancellation-requests",
        headers=headers(client, alias, key),
        json={"expected_version": row["version"], "reason": "合成取消意向", **extra},
    )


def decide(client, row, decision="ACCEPTED", alias="merchant-a", tenant=A, key=None, **extra):
    request_id = row["cancellation_requests"][-1]["id"]
    return client.post(
        base(tenant) + f"/reservations/{row['id']}/cancellation-requests/{request_id}/decision",
        headers=headers(client, alias, key),
        json={
            "expected_version": row["version"],
            "decision": decision,
            "response_note": "合成处理结果，对顾客可见",
            **extra,
        },
    )


def move(client, row, target):
    return client.post(
        base() + f"/reservations/{row['id']}/transitions",
        headers=headers(client, "merchant-a"),
        json={"expected_version": row["version"], "target_status": target},
    )


def test_request_intent_is_not_cancellation_and_merchant_acceptance_is_audited(client):
    original = create(client).json()
    response = cancel(client, original)
    assert response.status_code == 201
    row = response.json()
    assert row["status"] == "PENDING_CONFIRMATION" and row["version"] == 2
    assert row["events"][-1]["action"] == "CANCELLATION_REQUESTED"
    assert move(client, row, "CONFIRMED").json()["code"] == "CANCELLATION_REVIEW_REQUIRED"
    assert move(client, row, "CANCELLED").status_code == 409
    result = decide(client, row)
    assert result.status_code == 200 and result.json()["status"] == "CANCELLED"
    detail = client.get(
        "/api/v1/me/records/reservation/" + row["id"], headers=headers(client)
    ).json()
    assert detail["events"][-1]["action"] == "CANCELLATION_ACCEPTED"
    request = detail["cancellation_requests"][0]
    assert request["status"] == "ACCEPTED" and request["decided_version"] == 3
    assert "requester_id" not in request and "decision_actor_id" not in request
    assert detail["raw_text"] == original["raw_text"] and detail["items"] == original["items"]
    assert cancel(client, detail).status_code == 409


def test_reject_preserves_state_then_can_resume_or_submit_new_intent(client):
    row = move(client, create(client).json(), "CONFIRMED").json()
    row = move(client, row, "PREPARING").json()
    pending = cancel(client, row).json()
    assert pending["status"] == "PREPARING"
    assert move(client, pending, "READY").status_code == 409
    rejected = decide(client, pending, "REJECTED").json()
    assert rejected["status"] == "PREPARING"
    assert rejected["cancellation_requests"][0]["status"] == "REJECTED"
    new = cancel(client, rejected).json()
    assert len(new["cancellation_requests"]) == 2
    latest = decide(client, new, "REJECTED").json()
    assert move(client, latest, "READY").status_code == 200


def test_cancellation_ownership_tenant_and_no_name_claim(client):
    row = create(client).json()
    for alias in ("customer-b", "merchant-a", "merchant-b"):
        assert cancel(client, row, alias=alias).status_code == 404
    assert (
        client.post(
            f"/api/v1/me/reservations/{row['id']}/cancellation-requests",
            json={"expected_version": 1, "reason": "x"},
        ).status_code
        == 401
    )
    manual = client.post(
        base() + "/reservations",
        headers=headers(client, "merchant-a"),
        json={"customer_label": "customer-a", "raw_text": "电话代记"},
    ).json()
    assert cancel(client, manual).status_code == 404
    pending = cancel(client, row).json()
    for alias, tenant in (("merchant-b", B), ("merchant-b", A), ("customer-a", A)):
        assert decide(client, pending, alias=alias, tenant=tenant).status_code == 404
    another = cancel(client, create(client).json()).json()
    wrong = dict(pending, cancellation_requests=another["cancellation_requests"])
    assert decide(client, wrong).status_code == 404


def test_duplicate_keys_stale_versions_and_pending_uniqueness(client):
    row = create(client).json()
    key = str(uuid4())
    first = cancel(client, row, key=key)
    assert cancel(client, row, key=key).json() == first.json()
    assert cancel(client, row, key=key, reason="changed").status_code == 409
    assert cancel(client, row).json()["code"] == "VERSION_CONFLICT"
    pending = first.json()
    assert cancel(client, pending).json()["code"] == "CANCELLATION_ALREADY_PENDING"
    decision_key = str(uuid4())
    accepted = decide(client, pending, key=decision_key)
    assert accepted.status_code == 200
    assert decide(client, pending, key=decision_key).json() == accepted.json()
    assert decide(client, pending, key=decision_key, decision="REJECTED").status_code == 409
    assert decide(client, pending).status_code == 409


@pytest.mark.parametrize(
    "patch",
    [
        {"requester_id": "fake"},
        {"status": "CANCELLED"},
        {"tenant_id": B},
        {"reason": " "},
        {"expected_version": 0},
        {"reason": "x" * 501},
    ],
    ids=["spoof-owner", "spoof-status", "spoof-tenant", "empty", "version", "oversized"],
)
def test_reject_invalid_cancellation_inputs(client, patch):
    row = create(client).json()
    assert cancel(client, row, **patch).status_code == 422


def test_pending_list_is_scoped_and_resolved_disappears(client):
    row = cancel(client, create(client).json()).json()
    create(client)
    create(client, tenant=B)
    query = base() + "/reservations?cancellation_pending=true"
    data = client.get(query, headers=headers(client, "merchant-a")).json()
    assert data["total"] == 1 and data["items"][0]["id"] == row["id"]
    assert (
        client.get(
            base(B) + "/reservations?cancellation_pending=true",
            headers=headers(client, "merchant-b"),
        ).json()["total"]
        == 0
    )
    decide(client, row, "REJECTED")
    assert client.get(query, headers=headers(client, "merchant-a")).json()["total"] == 0


def test_concurrent_request_and_decision_have_single_winner(client, pg_settings):
    row = create(client).json()
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: cancel(client, row), range(5)))
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409, 409]
    pending = next(r.json() for r in results if r.status_code == 201)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: decide(client, pending), range(5)))
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409]
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CancellationRequest)) == 1
        assert session.scalar(select(func.count()).select_from(RecordEvent)) == 3
    engine.dispose()


def test_request_vs_fulfillment_transition_detects_conflict(client):
    row = move(client, create(client).json(), "CONFIRMED").json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(cancel, client, row)
        b = pool.submit(move, client, row, "PREPARING")
        codes = [a.result().status_code, b.result().status_code]
    assert codes in ([201, 409], [409, 200])


def test_transaction_failure_rolls_back_intent_version_and_events(client, pg_settings):
    row = create(client).json()

    def fail(session):
        if any(isinstance(obj, CancellationRequest) for obj in session.new):
            raise SQLAlchemyError("synthetic rollback")

    def before_flush(session, context, instances):
        fail(session)

    event.listen(Session, "before_flush", before_flush)
    try:
        assert cancel(client, row).status_code == 503
    finally:
        event.remove(Session, "before_flush", before_flush)
    detail = client.get(
        "/api/v1/me/records/reservation/" + row["id"], headers=headers(client)
    ).json()
    assert detail["version"] == 1 and not detail["cancellation_requests"]
    assert len(detail["events"]) == 1
    assert cancel(client, row).status_code == 201


def test_paused_store_history_allows_intent_but_not_new_business(client, pg_settings):
    row = create(client).json()
    engine = build_engine(pg_settings)
    with Session(engine) as session, session.begin():
        session.get(Tenant, UUID(A)).status = "SUSPENDED"
    assert cancel(client, row).status_code == 201
    assert create(client).status_code == 404
    engine.dispose()


def test_database_constraint_rejects_cross_tenant_reference(client, pg_settings):
    row = create(client).json()
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        user = session.get(Reservation, UUID(row["id"])).customer_user_id
        session.add(
            CancellationRequest(
                tenant_id=UUID(B),
                reservation_id=UUID(row["id"]),
                requester_id=user,
                reason="bad cross tenant",
                requested_version=2,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    engine.dispose()


def test_commit_failure_rolls_back_merchant_decision_and_retry_succeeds(client):
    row = cancel(client, create(client).json()).json()
    key = str(uuid4())

    def fail(session):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        assert decide(client, row, key=key).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    detail = client.get(
        "/api/v1/me/records/reservation/" + row["id"], headers=headers(client)
    ).json()
    assert detail["status"] == "PENDING_CONFIRMATION" and detail["version"] == row["version"]
    assert detail["cancellation_requests"][0]["status"] == "REQUESTED"
    assert decide(client, row, key=key).status_code == 200
