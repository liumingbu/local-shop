import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from local_shop.db import build_engine
from local_shop.main import create_app
from local_shop.models import Inquiry, InquiryEvent, InquiryReply, Tenant
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)
A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"


@pytest.fixture
def client(pg_settings):
    with TestClient(create_app(pg_settings), client=("127.0.0.1", 55001)) as app:
        app.tokens = {
            alias: app.post("/api/v1/dev/session", json={"identity": alias}).json()["access_token"]
            for alias in ("merchant-a", "merchant-b", "customer-a", "customer-b")
        }
        for tenant, owner in ((A, "merchant-a"), (B, "merchant-b")):
            assert (
                app.put(
                    base(tenant) + "/store",
                    headers=headers(app, owner),
                    json={
                        "name": "合成店",
                        "expected_version": 0,
                        "published": True,
                        "allow_pickup": True,
                        "allow_delivery": True,
                    },
                ).status_code
                == 200
            )
        yield app


def headers(client, alias="customer-a", key=None):
    return {
        "Authorization": "Bearer " + client.tokens[alias],
        "Idempotency-Key": key or str(uuid4()),
    }


def base(tenant=A):
    return f"/api/v1/merchant/tenants/{tenant}"


def create(client, alias="customer-a", tenant=A, key=None, **extra):
    return client.post(
        f"/api/v1/stores/{tenant}/reservations",
        headers=headers(client, alias, key),
        json={"raw_text": "合成顾客原始需求", "privacy_accepted": True, **extra},
    )


def inquire(client, alias="customer-a", tenant=A, key=None, **extra):
    return client.post(
        f"/api/v1/stores/{tenant}/inquiries",
        headers=headers(client, alias, key),
        json={"raw_text": "这款有货吗？合成询货", "privacy_accepted": True, **extra},
    )


def reply(client, row, alias="merchant-a", tenant=A, key=None, **extra):
    return client.post(
        base(tenant) + f"/inquiries/{row['id']}/replies",
        headers=headers(client, alias, key),
        json={
            "text": "合成答复",
            "visible_to_customer": True,
            "expected_version": row["version"],
            **extra,
        },
    )


def convert(client, row, alias="merchant-a", tenant=A, key=None, **extra):
    return client.post(
        base(tenant) + f"/inquiries/{row['id']}/convert",
        headers=headers(client, alias, key),
        json={
            "customer_label": "合成顾客",
            "raw_text": "明确转换后的确认内容",
            "expected_version": row["version"],
            **extra,
        },
    )


def test_customer_record_ownership_store_scope_and_merchant_isolation(client):
    a = create(client).json()
    b = create(client, "customer-b").json()
    other_store = create(client, tenant=B).json()
    mine = client.get(f"/api/v1/me/records?store_id={A}", headers=headers(client)).json()
    assert mine["total"] == 1 and mine["items"][0]["id"] == a["id"]
    assert (
        client.get("/api/v1/me/records/reservation/" + b["id"], headers=headers(client)).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/me/records/reservation/" + a["id"], headers=headers(client, "merchant-b")
        ).status_code
        == 404
    )
    assert (
        client.get(
            base(B) + "/reservations/" + a["id"], headers=headers(client, "merchant-b")
        ).status_code
        == 404
    )
    assert (
        client.get(
            base() + "/reservations/" + a["id"], headers=headers(client, "merchant-a")
        ).status_code
        == 200
    )
    assert client.get(base() + "/reservations", headers=headers(client)).status_code == 404
    all_mine = client.get("/api/v1/me/records", headers=headers(client)).json()
    assert {row["id"] for row in all_mine["items"]} == {a["id"], other_store["id"]}
    assert not {"internal_note", "actor_id", "customer_user_id"} & mine["items"][0].keys()


def test_manual_same_name_does_not_bind_customer(client):
    response = client.post(
        base() + "/reservations",
        headers=headers(client, "merchant-a"),
        json={"customer_label": "customer-a", "raw_text": "同名代录", "internal_note": "内部秘密"},
    )
    assert response.status_code == 201 and response.json()["customer_user_id"] is None
    assert client.get("/api/v1/me/records", headers=headers(client)).json()["total"] == 0
    assert (
        client.get(
            "/api/v1/me/records/reservation/" + response.json()["id"], headers=headers(client)
        ).status_code
        == 404
    )


def test_customer_cannot_set_owner_or_merchant_fields(client):
    for patch in (
        {"customer_user_id": "00000000-0000-4000-8000-000000000004"},
        {"source": "MERCHANT_PHONE"},
        {"mark_confirmed": True},
        {"internal_note": "x"},
        {"status": "COMPLETED"},
        {"openid": "spoof"},
        {"tenant_id": B},
    ):
        assert create(client, **patch).status_code == 422
    row = create(client).json()
    assert (
        client.post(
            base() + f"/reservations/{row['id']}/transitions",
            headers=headers(client),
            json={"target_status": "COMPLETED", "expected_version": 1},
        ).status_code
        == 404
    )


def test_customer_idempotency_scoped_to_actor_and_store(client):
    key = str(uuid4())
    first = create(client, key=key)
    again = create(client, key=key)
    assert first.status_code == 201 and first.json() == again.json()
    assert create(client, key=key, raw_text="改变载荷").status_code == 409
    assert create(client, "customer-b", key=key).json()["id"] != first.json()["id"]
    assert create(client, tenant=B, key=key).json()["id"] != first.json()["id"]


def test_customer_concurrent_duplicate_requests(client):
    key = str(uuid4())
    with ThreadPoolExecutor(5) as pool:
        responses = list(pool.map(lambda _: create(client, key=key), range(5)))
    assert all(r.status_code == 201 for r in responses)
    assert len({r.json()["id"] for r in responses}) == 1


def test_store_publication_delivery_configuration_and_consent(client):
    assert create(client, privacy_accepted=False).status_code == 422
    assert (
        client.post(
            f"/api/v1/stores/{A}/reservations",
            headers=headers(client),
            json={"raw_text": "缺少同意"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            base() + "/store",
            headers=headers(client, "merchant-a"),
            json={"name": "合成店", "expected_version": 1, "allow_delivery": False},
        ).status_code
        == 200
    )
    assert create(client, fulfillment_method="DELIVERY").status_code == 409
    assert create(client).status_code == 201
    assert (
        client.put(
            base() + "/store",
            headers=headers(client, "merchant-a"),
            json={"name": "合成店", "expected_version": 2, "published": False},
        ).status_code
        == 200
    )
    assert create(client).status_code == 404 and inquire(client).status_code == 404


def test_expected_time_is_timezone_aware_and_items_only_supported(client):
    assert create(client, expected_at="2030-01-01T12:30:00").status_code == 422
    response = create(
        client,
        raw_text="",
        items=[{"name": "合成自由品", "quantity": "0.5", "unit": "斤"}],
        expected_at="2030-01-01T12:30:00+08:00",
    )
    assert response.status_code == 201 and response.json()["expected_at"] is not None
    assert response.json()["items"][0]["quantity"] == "0.5"
    assert create(client, raw_text="", items=[]).status_code == 422


def test_inquiry_reply_does_not_make_reservation_and_internal_reply_hidden(client):
    row = inquire(client).json()
    assert row["status"] == "NEW"
    internal = reply(client, row, text="内部不可公开备注", visible_to_customer=False)
    assert internal.status_code == 201 and internal.json()["status"] == "NEW"
    own = client.get("/api/v1/me/records/inquiry/" + row["id"], headers=headers(client))
    assert "内部不可公开备注" not in own.text and own.json()["replies"] == []
    assert "INTERNAL_NOTE" not in own.text
    public = reply(client, internal.json(), text="有货，需要多少？")
    assert public.status_code == 201 and public.json()["status"] == "REPLIED"
    assert (
        client.get(base() + "/reservations", headers=headers(client, "merchant-a")).json()["total"]
        == 0
    )
    own = client.get("/api/v1/me/records/inquiry/" + row["id"], headers=headers(client)).json()
    assert len(own["replies"]) == 1 and own["replies"][0]["text"] == "有货，需要多少？"


def test_inquiry_customer_and_merchant_cross_tenant_access(client):
    row = inquire(client).json()
    assert (
        client.get(
            "/api/v1/me/records/inquiry/" + row["id"], headers=headers(client, "customer-b")
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/me/records?kind=inquiry", headers=headers(client, "customer-b")).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get(base() + "/inquiries", headers=headers(client, "merchant-b")).status_code == 404
    )
    assert (
        client.get(
            base(B) + "/inquiries/" + row["id"], headers=headers(client, "merchant-b")
        ).status_code
        == 404
    )
    assert reply(client, row, alias="merchant-b").status_code == 404
    assert reply(client, row, alias="merchant-b", tenant=B).status_code == 404
    assert convert(client, row, alias="merchant-b", tenant=B).status_code == 404
    assert reply(client, row, alias="customer-a").status_code == 404


def test_explicit_conversion_is_owned_idempotent_and_retains_original(client):
    inquiry = inquire(client).json()
    key = str(uuid4())
    first = convert(client, inquiry, key=key, internal_note="转换内部备注")
    assert first.status_code == 201
    row = first.json()
    assert row["status"] == "PENDING_CONFIRMATION" and row["raw_text"] == inquiry["raw_text"]
    assert row["confirmed_text"] == "明确转换后的确认内容"
    assert convert(client, inquiry, key=key, internal_note="转换内部备注").json() == row
    current = client.get(
        base() + "/inquiries/" + inquiry["id"], headers=headers(client, "merchant-a")
    ).json()
    assert current["status"] == "NEW" and current["converted_reservation_id"] == row["id"]
    assert convert(client, current).status_code == 409
    mine = client.get("/api/v1/me/records/reservation/" + row["id"], headers=headers(client))
    assert mine.status_code == 200 and "转换内部备注" not in mine.text
    assert mine.json()["confirmed_text"] == "明确转换后的确认内容"
    assert (
        client.get(
            "/api/v1/me/records/reservation/" + row["id"], headers=headers(client, "customer-b")
        ).status_code
        == 404
    )


def test_concurrent_conversion_cannot_create_two_records(client):
    row = inquire(client).json()
    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda _: convert(client, row).status_code, range(2)))
    assert sorted(codes) == [201, 409]
    assert (
        client.get(base() + "/reservations", headers=headers(client, "merchant-a")).json()["total"]
        == 1
    )


def test_reply_versions_idempotency_and_closed_state(client):
    row = inquire(client).json()
    key = str(uuid4())
    first = reply(client, row, key=key)
    assert reply(client, row, key=key).json() == first.json()
    assert reply(client, row).status_code == 409
    current = first.json()
    closed = client.post(
        base() + f"/inquiries/{row['id']}/close",
        headers=headers(client, "merchant-a"),
        json={"expected_version": current["version"]},
    )
    assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"
    assert reply(client, closed.json()).status_code == 409
    assert convert(client, closed.json()).status_code == 409


def test_customer_status_history_hides_internal_notes_and_actor(client):
    row = create(client).json()
    first = client.post(
        base() + f"/reservations/{row['id']}/transitions",
        headers=headers(client, "merchant-a"),
        json={
            "target_status": "CONFIRMED",
            "expected_version": 1,
            "note": "私有备货说明",
            "visible_to_customer": False,
        },
    )
    assert first.status_code == 200
    mine = client.get("/api/v1/me/records/reservation/" + row["id"], headers=headers(client))
    assert (
        mine.status_code == 200 and "私有备货说明" not in mine.text and "actor_id" not in mine.text
    )
    assert mine.json()["events"][-1]["to_status"] == "CONFIRMED"
    assert (
        client.post(
            base() + f"/reservations/{row['id']}/transitions",
            headers=headers(client, "merchant-a"),
            json={
                "target_status": "PREPARING",
                "expected_version": 2,
                "note": "开始备货",
                "visible_to_customer": True,
            },
        ).status_code
        == 200
    )
    assert (
        "开始备货"
        in client.get("/api/v1/me/records/reservation/" + row["id"], headers=headers(client)).text
    )


def test_suspension_blocks_new_customer_requests_but_preserves_owned_history(client, pg_settings):
    row = create(client).json()
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session, session.begin():
            session.get(Tenant, UUID(A)).status = "SUSPENDED"
        assert create(client).status_code == 404 and inquire(client).status_code == 404
        assert (
            client.get(
                "/api/v1/me/records/reservation/" + row["id"], headers=headers(client)
            ).status_code
            == 200
        )
    finally:
        engine.dispose()


def test_customer_inquiry_commit_failure_rolls_back_everything(client, pg_settings):
    def fail(session):
        raise SQLAlchemyError("synthetic failure")

    event.listen(Session, "before_commit", fail)
    try:
        assert inquire(client).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session:
            for model in (Inquiry, InquiryEvent, InquiryReply):
                assert session.scalar(select(func.count()).select_from(model)) == 0
    finally:
        engine.dispose()


def test_unauthenticated_and_disabled_customer_cannot_use_private_records(client, pg_settings):
    assert client.get("/api/v1/me/records").status_code == 401
    assert (
        client.post(
            f"/api/v1/stores/{A}/inquiries",
            headers={"Idempotency-Key": "missing-auth"},
            json={"raw_text": "x", "privacy_accepted": True},
        ).status_code
        == 401
    )
    from local_shop.models import User

    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session, session.begin():
            session.get(User, UUID("00000000-0000-4000-8000-000000000003")).status = "DISABLED"
        assert create(client).status_code == 401
    finally:
        engine.dispose()


def test_customer_pagination_and_no_public_record_route(client):
    for _ in range(3):
        assert inquire(client).status_code == 201
    result = client.get(
        "/api/v1/me/records?kind=inquiry&page=2&limit=2", headers=headers(client)
    ).json()
    assert result["total"] == 3 and len(result["items"]) == 1
    assert client.get("/api/v1/me/records?limit=1000", headers=headers(client)).status_code == 422
    assert client.get(f"/api/v1/stores/{A}/inquiries/{result['items'][0]['id']}").status_code == 404


def test_inquiry_idempotency_and_cross_store_product_snapshot(client):
    def product(tenant, alias):
        cat = client.post(
            base(tenant) + "/categories", headers=headers(client, alias), json={"name": "询货分类"}
        ).json()
        payload = {
            "category_id": cat["id"],
            "name": "询货原商品",
            "unit": "盒",
            "spec": "原规格",
            "status": "PUBLISHED",
        }
        response = client.post(
            base(tenant) + "/products", headers=headers(client, alias), json=payload
        )
        assert response.status_code == 201
        return response.json(), payload

    own, payload = product(A, "merchant-a")
    foreign, _ = product(B, "merchant-b")
    assert inquire(client, product_id=foreign["id"]).status_code == 404
    assert (
        create(
            client,
            items=[{"product_id": foreign["id"], "name": "x", "quantity": "1", "unit": "盒"}],
        ).status_code
        == 404
    )
    key = str(uuid4())
    first = inquire(client, key=key, product_id=own["id"])
    assert first.status_code == 201
    assert inquire(client, key=key, product_id=own["id"]).json() == first.json()
    assert inquire(client, key=key, product_id=own["id"], raw_text="改变").status_code == 409
    assert (
        client.put(
            base() + "/products/" + own["id"],
            headers=headers(client, "merchant-a"),
            json=payload
            | {"name": "新名字", "status": "ARCHIVED", "expected_version": own["version"]},
        ).status_code
        == 200
    )
    detail = client.get(
        "/api/v1/me/records/inquiry/" + first.json()["id"], headers=headers(client)
    ).json()
    assert detail["product_snapshot"]["name"] == "询货原商品"
    assert inquire(client, product_id=own["id"]).status_code == 404


def test_downgrade_refuses_to_discard_customer_content(client, pg_settings):
    from conftest import migrate

    row = inquire(client).json()
    with pytest.raises(AssertionError, match="Migration failed"):
        migrate(pg_settings, "downgrade", "0004_media")
    assert (
        client.get("/api/v1/me/records/inquiry/" + row["id"], headers=headers(client)).status_code
        == 200
    )
