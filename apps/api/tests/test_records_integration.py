import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from local_shop.db import build_engine
from local_shop.main import create_app
from local_shop.models import IdempotencyKey, RecordEvent, Reservation, Tenant, TenantMember
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)
A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"


@pytest.fixture
def api(pg_settings):
    with TestClient(create_app(pg_settings), client=("127.0.0.1", 55001)) as client:
        tokens = {}
        for alias in ("merchant-a", "merchant-b"):
            tokens[alias] = client.post("/api/v1/dev/session", json={"identity": alias}).json()[
                "access_token"
            ]
        yield client, tokens


def headers(api, alias="merchant-a", key=None):
    value = {"Authorization": "Bearer " + api[1][alias]}
    if key is not None:
        value["Idempotency-Key"] = key
    return value


def base(tenant=A):
    return f"/api/v1/merchant/tenants/{tenant}"


def create(api, tenant=A, alias="merchant-a", key=None, **extra):
    return api[0].post(
        base(tenant) + "/reservations",
        headers=headers(api, alias, key or str(uuid4())),
        json={"customer_label": "合成顾客甲", "raw_text": "电话需求原文，半斤分两袋", **extra},
    )


def move(api, record, target, alias="merchant-a", tenant=A, version=None, key=None):
    return api[0].post(
        base(tenant) + f"/reservations/{record['id']}/transitions",
        headers=headers(api, alias, key or str(uuid4())),
        json={"target_status": target, "expected_version": version or record["version"]},
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("PICKUP", ["CONFIRMED", "PREPARING", "READY", "COMPLETED"]),
        ("DELIVERY", ["CONFIRMED", "PREPARING", "READY", "OUT_FOR_DELIVERY", "COMPLETED"]),
    ],
)
def test_owner_complete_loop(api, method, path):
    client = api[0]
    shop = client.put(
        base() + "/store", headers=headers(api), json={"name": "合成店A", "expected_version": 0}
    )
    assert shop.status_code == 200
    response = create(api, fulfillment_method=method)
    assert response.status_code == 201, response.text
    record = response.json()
    for status in path:
        response = move(api, record, status)
        assert response.status_code == 200, response.text
        record = response.json()
    detail = client.get(base() + f"/reservations/{record['id']}", headers=headers(api)).json()
    assert detail["raw_text"] == "电话需求原文，半斤分两袋"
    assert [e["to_status"] for e in detail["events"]] == ["PENDING_CONFIRMATION", *path]
    listing = client.get(base() + "/reservations?status=COMPLETED", headers=headers(api)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == record["id"]
    assert move(api, record, "CANCELLED").status_code == 409


def test_all_merchant_routes_require_identity(api):
    assert api[0].get("/api/v1/merchant/tenants").status_code == 401
    assert api[0].get(base() + "/reservations").status_code == 401
    assert (
        api[0].put(base() + "/store", json={"name": "x", "expected_version": 0}).status_code == 401
    )


def test_tenant_visibility_and_cross_access(api):
    client = api[0]
    record = create(api).json()
    for alias, tid, other in [("merchant-a", A, B), ("merchant-b", B, A)]:
        visible = client.get("/api/v1/merchant/tenants", headers=headers(api, alias)).json()[
            "items"
        ]
        assert [t["id"] for t in visible] == [tid]
        assert (
            client.get(base(other) + "/reservations", headers=headers(api, alias)).status_code
            == 404
        )
        assert create(api, tenant=other, alias=alias).status_code == 404
        assert client.get(base(other) + "/store", headers=headers(api, alias)).status_code == 404
        assert (
            client.put(
                base(other) + "/store",
                headers=headers(api, alias),
                json={"name": "x", "expected_version": 0},
            ).status_code
            == 404
        )
    assert (
        client.get(
            base(B) + f"/reservations/{record['id']}", headers=headers(api, "merchant-b")
        ).status_code
        == 404
    )
    assert move(api, record, "CONFIRMED", alias="merchant-b", tenant=B).status_code == 404
    assert move(api, record, "CONFIRMED", alias="merchant-b", tenant=A).status_code == 404
    assert (
        client.get(base(B) + "/reservations", headers=headers(api, "merchant-b")).json()["total"]
        == 0
    )


def test_create_idempotent_and_conflict(api):
    key = str(uuid4())
    first = create(api, key=key)
    assert first.status_code == 201
    assert create(api, key=key).json() == first.json()
    assert create(api, key=key, raw_text="changed").status_code == 409
    assert api[0].get(base() + "/reservations", headers=headers(api)).json()["total"] == 1


def test_concurrent_duplicate_create(api):
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: create(api, key=key), range(10)))
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    assert len({r.json()["id"] for r in results}) == 1
    assert api[0].get(base() + "/reservations", headers=headers(api)).json()["total"] == 1


def test_transition_idempotency_and_version(api):
    record = create(api).json()
    key = str(uuid4())
    response = move(api, record, "CONFIRMED", key=key)
    assert response.status_code == 200
    assert move(api, record, "CONFIRMED", key=key).json() == response.json()
    assert move(api, record, "CANCELLED", key=key).status_code == 409
    assert move(api, record, "PREPARING").status_code == 409


def test_concurrent_versions_only_one_wins(api):
    record = create(api).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda target: move(api, record, target), ["CONFIRMED", "CANCELLED"])
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    detail = api[0].get(base() + f"/reservations/{record['id']}", headers=headers(api)).json()
    assert detail["version"] == 2 and len(detail["events"]) == 2


def test_illegal_state_and_method_transition(api):
    record = create(api, mark_confirmed=True).json()
    assert record["version"] == 2
    assert move(api, record, "COMPLETED").status_code == 409
    record = move(api, record, "PREPARING").json()
    record = move(api, record, "READY").json()
    assert move(api, record, "OUT_FOR_DELIVERY").status_code == 409
    record = move(api, record, "CANCELLED").json()
    assert move(api, record, "CONFIRMED").status_code == 409


def test_decimal_units_and_no_customer_auto_binding(api):
    record = create(
        api,
        items=[
            {"name": "合成商品", "quantity": "0.5", "unit": "斤"},
            {"name": "合成商品", "quantity": "1.25", "unit": "盒"},
        ],
    ).json()
    assert record["items"][0]["quantity"] == "0.5"
    assert [x["unit"] for x in record["items"]] == ["斤", "盒"]
    assert "customer_user_id" not in record
    assert create(api, customer_user_id="00000000-0000-4000-8000-000000000002").status_code == 422
    assert create(api, tenant_id=B).status_code == 422


@pytest.mark.parametrize(
    "patch",
    [
        {"raw_text": " "},
        {"customer_label": ""},
        {"items": [{"name": "x", "quantity": "-1", "unit": "斤"}]},
        {"items": [{"name": "x", "quantity": "0.0001", "unit": "斤"}]},
        {"items": [{"name": "x", "quantity": "1", "unit": ""}]},
        {"items": [{"name": "x", "quantity": "NaN", "unit": "斤"}]},
        {"items": [{"name": "x", "quantity": "1", "unit": "斤", "product_id": "not-a-uuid"}]},
    ],
)
def test_invalid_payloads(api, patch):
    assert create(api, **patch).status_code == 422


def test_idempotency_key_required_and_validated(api):
    url = base() + "/reservations"
    data = {"customer_label": "合成", "raw_text": "text"}
    assert api[0].post(url, headers=headers(api), json=data).status_code == 422
    assert api[0].post(url, headers=headers(api, key="short"), json=data).status_code == 422


def test_suspended_tenant_and_disabled_membership(api, pg_settings):
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session, session.begin():
            session.get(Tenant, UUID(A)).status = "SUSPENDED"
        assert create(api).status_code == 404
        with Session(engine) as session, session.begin():
            session.get(Tenant, UUID(A)).status = "ACTIVE"
            member = session.get(
                TenantMember, (UUID(A), UUID("00000000-0000-4000-8000-000000000001"))
            )
            member.status = "DISABLED"
        assert create(api).status_code == 404
    finally:
        engine.dispose()


def test_atomic_rollback_on_idempotency_failure(api, pg_settings):
    def fail(*args):
        raise RuntimeError("intentional persistence failure")

    event.listen(IdempotencyKey, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="intentional"):
            create(api)
    finally:
        event.remove(IdempotencyKey, "before_insert", fail)
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session:
            for model in (Reservation, RecordEvent, IdempotencyKey):
                assert session.scalar(select(func.count()).select_from(model)) == 0
    finally:
        engine.dispose()


def test_database_rejects_cross_tenant_event(api, pg_settings):
    record = create(api).json()
    engine = build_engine(pg_settings)
    try:
        with pytest.raises(IntegrityError):
            with Session(engine) as session, session.begin():
                session.add(
                    RecordEvent(
                        tenant_id=UUID(B),
                        reservation_id=UUID(record["id"]),
                        actor_id=UUID("00000000-0000-4000-8000-000000000002"),
                        version=2,
                        to_status="CONFIRMED",
                    )
                )
                session.flush()
    finally:
        engine.dispose()


def test_store_version_and_pagination(api):
    client = api[0]
    url = base() + "/store"
    assert (
        client.put(url, headers=headers(api), json={"name": "A", "expected_version": 0}).status_code
        == 200
    )
    assert (
        client.put(url, headers=headers(api), json={"name": "B", "expected_version": 0}).status_code
        == 409
    )
    assert client.get(url, headers=headers(api)).json()["name"] == "A"
    for _ in range(3):
        assert create(api).status_code == 201
    response = client.get(base() + "/reservations?limit=2&page=2", headers=headers(api)).json()
    assert response["total"] == 3 and len(response["items"]) == 1
    assert client.get(base() + "/reservations?limit=1000", headers=headers(api)).status_code == 422


def test_commit_failure_returns_error_and_rolls_back(api, pg_settings):
    def fail_commit(session):
        raise SQLAlchemyError("intentional secret-like database detail")

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = create(api)
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_UNAVAILABLE"
        assert "secret-like" not in response.text
    finally:
        event.remove(Session, "before_commit", fail_commit)
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session:
            for model in (Reservation, RecordEvent, IdempotencyKey):
                assert session.scalar(select(func.count()).select_from(model)) == 0
    finally:
        engine.dispose()
