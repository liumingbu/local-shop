"""Existing committed events, per-user/read scopes and private manual contact outcomes."""

import os
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from local_shop.communication_models import ContactRecord, NotificationAttempt
from local_shop.db import build_engine
from local_shop.external_notifications import ProviderResult, dispatch_once, prepare
from local_shop.main import create_app
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_records_integration import A, B, api, base, headers, move

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
__all__ = ["api"]
OWNER = UUID("00000000-0000-4000-8000-000000000001")


def setup_customer(api, tenant=A, owner="merchant-a", alias="customer-a"):
    r = api[0].put(
        base(tenant) + "/store",
        headers=headers(api, owner),
        json={"name": "合成沟通店", "expected_version": 0, "published": True, "allow_pickup": True},
    )
    assert r.status_code == 200, r.text
    return api[0].post("/api/v1/dev/session", json={"identity": alias}).json()["access_token"]


def customer_record(api, token, tenant=A, key=None, kind="reservations"):
    body = {"raw_text": "合成需求，不含真实资料", "privacy_accepted": True}
    if kind == "reservations":
        body["customer_label"] = "合成顾客"
    r = api[0].post(
        f"/api/v1/stores/{tenant}/{kind}",
        headers={"Authorization": "Bearer " + token, "Idempotency-Key": key or str(uuid4())},
        json=body,
    )
    assert r.status_code == 201, r.text
    return r.json()


def updates(api, token=None, tenant=A, alias="merchant-a"):
    root = f"/api/v1/me/stores/{tenant}" if token else base(tenant)
    h = {"Authorization": "Bearer " + token} if token else headers(api, alias)
    r = api[0].get(root + "/updates", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def mark(api, keys, token=None, tenant=A, alias="merchant-a"):
    root = f"/api/v1/me/stores/{tenant}" if token else base(tenant)
    h = {"Authorization": "Bearer " + token} if token else headers(api, alias)
    return api[0].post(root + "/updates/read", headers=h, json={"event_keys": keys})


def test_idempotent_business_events_read_is_not_processing_or_customer_read(api, pg_settings):
    token = setup_customer(api)
    key = str(uuid4())
    row = customer_record(api, token, key=key)
    assert customer_record(api, token, key=key)["id"] == row["id"]
    feed = updates(api)
    assert feed["unread"] == 1 and feed["total"] == 1
    assert updates(api, token)["unread"] == 0
    assert mark(api, [feed["items"][0]["event_key"]]).status_code == 200
    assert updates(api)["unread"] == 0
    current = api[0].get(base() + f"/reservations/{row['id']}", headers=headers(api)).json()
    assert current["status"] == "PENDING_CONFIRMATION"
    assert (
        api[0]
        .get(base() + "/workbench-summary", headers=headers(api))
        .json()["counts"]["PENDING_CONFIRMATION"]
        == 1
    )
    changed = move(api, row, "CONFIRMED")
    assert changed.status_code == 200
    customer = updates(api, token)
    assert customer["unread"] == 1
    assert mark(api, [feed["items"][0]["event_key"]]).status_code == 200
    assert updates(api, token)["unread"] == 1
    with TestClient(create_app(pg_settings), client=("127.0.0.1", 55002)) as restarted:
        assert restarted.get(base() + "/updates", headers=headers(api)).json()["unread"] == 0
    assert mark(api, [customer["items"][0]["event_key"]], token).status_code == 200
    assert updates(api, token)["unread"] == 0


def test_updates_and_read_markers_never_cross_store_or_customer(api):
    ca = setup_customer(api)
    setup_customer(api, B, "merchant-b")
    ra = customer_record(api, ca)
    rb = customer_record(api, ca, B)
    fa = updates(api)
    fb = updates(api, tenant=B, alias="merchant-b")
    assert ra["id"] != rb["id"]
    assert mark(api, [fb["items"][0]["event_key"]]).status_code == 404
    assert mark(api, [fa["items"][0]["event_key"]]).status_code == 200
    assert updates(api, tenant=B, alias="merchant-b")["unread"] == 1
    assert api[0].get(base(B) + "/updates", headers=headers(api)).status_code == 404
    assert move(api, ra, "CONFIRMED").status_code == 200
    customer = updates(api, ca)
    cb = api[0].post("/api/v1/dev/session", json={"identity": "customer-b"}).json()["access_token"]
    assert updates(api, cb)["total"] == 0
    assert mark(api, [customer["items"][0]["event_key"]], cb).status_code == 404
    assert (
        api[0]
        .get(
            "/api/v1/me/records/reservation/" + ra["id"], headers={"Authorization": "Bearer " + cb}
        )
        .status_code
        == 404
    )


def test_public_reply_not_internal_reply_produces_customer_update(api):
    token = setup_customer(api)
    row = customer_record(api, token, kind="inquiries")
    assert updates(api)["unread"] == 1
    path = base() + f"/inquiries/{row['id']}/replies"
    private = api[0].post(
        path,
        headers=headers(api, key=str(uuid4())),
        json={
            "expected_version": row["version"],
            "text": "PRIVATE_INTERNAL_REPLY",
            "visible_to_customer": False,
        },
    )
    assert private.status_code == 201, private.text
    assert updates(api, token)["total"] == 0
    key = str(uuid4())
    body = {
        "expected_version": private.json()["version"],
        "text": "公开合成答复",
        "visible_to_customer": True,
    }
    first = api[0].post(path, headers=headers(api, key=key), json=body)
    assert first.status_code == 201
    assert api[0].post(path, headers=headers(api, key=key), json=body).json() == first.json()
    customer = updates(api, token)
    assert customer["total"] == 1 and "PRIVATE_INTERNAL_REPLY" not in str(customer)


@pytest.mark.parametrize("kind", ["reservations", "inquiries"])
def test_explicit_contact_internal_only_and_does_not_notify_or_resolve(api, pg_settings, kind):
    token = setup_customer(api)
    row = customer_record(api, token, kind=kind)
    root = base() + f"/{kind}/{row['id']}"
    before = updates(api, token)["total"]
    data = {
        "expected_version": row["version"],
        "method": "NOT_REACHED",
        "note": "PRIVATE_CONTACT_NOTE",
        "confirmed": False,
    }
    assert (
        api[0]
        .post(root + "/contacts", headers=headers(api, key=str(uuid4())), json=data)
        .status_code
        == 422
    )
    key = str(uuid4())
    data["confirmed"] = True
    response = api[0].post(root + "/contacts", headers=headers(api, key=key), json=data)
    assert response.status_code == 201, response.text
    assert (
        api[0].post(root + "/contacts", headers=headers(api, key=key), json=data).json()
        == response.json()
    )
    saved = api[0].get(root, headers=headers(api)).json()
    assert saved["status"] == row["status"] and saved["version"] == row["version"] + 1
    logs = api[0].get(root + "/contacts", headers=headers(api)).json()
    assert logs["total"] == 1 and logs["items"][0]["method"] == "NOT_REACHED"
    singular = "inquiry" if kind == "inquiries" else "reservation"
    public = api[0].get(
        f"/api/v1/me/records/{singular}/{row['id']}", headers={"Authorization": "Bearer " + token}
    )
    assert (
        public.status_code == 200
        and "PRIVATE_CONTACT_NOTE" not in public.text
        and "CONTACT_LOGGED" not in public.text
    )
    assert updates(api, token)["total"] == before
    assert (
        api[0].get(root + "/contacts", headers={"Authorization": "Bearer " + token}).status_code
        == 404
    )
    assert (
        api[0]
        .get(base(B) + f"/{kind}/{row['id']}/contacts", headers=headers(api, "merchant-b"))
        .status_code
        == 404
    )
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ContactRecord)) == 1
    engine.dispose()


def test_contact_draft_is_review_only_and_never_creates_log(api):
    token = setup_customer(api)
    row = customer_record(api, token)
    root = base() + f"/reservations/{row['id']}"
    assert api[0].get(root + "/contact-draft", headers=headers(api)).status_code == 409
    changed = move(api, row, "CONFIRMED")
    assert changed.status_code == 200
    response = api[0].get(root + "/contact-draft", headers=headers(api))
    assert response.status_code == 200, response.text
    assert (
        response.json()["review_required"]
        and not response.json()["sent"]
        and not response.json()["logged_contact"]
    )
    assert api[0].get(root + "/contacts", headers=headers(api)).json()["total"] == 0


def test_transaction_failure_leaves_no_business_notice_then_original_retry_succeeds(api):
    token = setup_customer(api)
    key = str(uuid4())

    def fail(session):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        response = api[0].post(
            "/api/v1/stores/" + A + "/reservations",
            headers={"Authorization": "Bearer " + token, "Idempotency-Key": key},
            json={
                "raw_text": "合成需求，不含真实资料",
                "privacy_accepted": True,
                "customer_label": "合成顾客",
            },
        )
        assert response.status_code == 503, response.text
    finally:
        event.remove(Session, "before_commit", fail)
    assert updates(api)["total"] == 0
    customer_record(api, token, key=key)
    assert updates(api)["total"] == 1


@pytest.mark.parametrize(
    "status", ["UNCONFIGURED", "REJECTED", "TIMEOUT", "FAILED", "ACCEPTED", "UNKNOWN"]
)
def test_external_boundary_never_claims_delivery_read_or_automatic_retry(api, pg_settings, status):
    token = setup_customer(api)
    customer_record(api, token)
    key = updates(api)["items"][0]["event_key"]
    engine = build_engine(pg_settings)

    class Fake:
        calls = 0

        def send(self, notice, deduplication_key):
            self.calls += 1
            assert notice["event_key"] == key and deduplication_key
            if status == "TIMEOUT":
                raise TimeoutError("PRIVATE_PROVIDER_ERROR_MUST_NOT_BE_STORED")
            return ProviderResult(status)

    fake = Fake()
    with Session(engine) as session, session.begin():
        identifier = prepare(session, UUID(A), OWNER, "MERCHANT", key)
    with Session(engine) as session, session.begin():
        assert prepare(session, UUID(A), OWNER, "MERCHANT", key) == identifier
    result = dispatch_once(engine, identifier, None if status == "UNCONFIGURED" else fake)
    assert result["status"] == status and result["request_accepted"] == (status == "ACCEPTED")
    assert not result["delivered"] and not result["read"] and not result["automatic_retry"]
    assert dispatch_once(engine, identifier, fake) == result
    assert fake.calls == (0 if status == "UNCONFIGURED" else 1)
    with Session(engine) as session:
        row = session.get(NotificationAttempt, identifier)
        assert (
            row.delivered_at is None
            and row.read_at is None
            and "PRIVATE_PROVIDER" not in row.result_code
        )
    engine.dispose()


def test_external_prepare_rollback_and_interrupted_dispatch_do_not_send_again(api, pg_settings):
    token = setup_customer(api)
    customer_record(api, token)
    key = updates(api)["items"][0]["event_key"]
    engine = build_engine(pg_settings)
    with pytest.raises(RuntimeError):
        with Session(engine) as session, session.begin():
            lost = prepare(session, UUID(A), OWNER, "MERCHANT", key)
            raise RuntimeError("synthetic rollback")
    with pytest.raises(HTTPException):
        dispatch_once(engine, lost)
    with Session(engine) as session, session.begin():
        identifier = prepare(session, UUID(A), OWNER, "MERCHANT", key)

    class Interrupted:
        calls = 0

        def send(self, *_):
            self.calls += 1
            raise KeyboardInterrupt("synthetic process interruption")

    fake = Interrupted()
    with pytest.raises(KeyboardInterrupt):
        dispatch_once(engine, identifier, fake)
    result = dispatch_once(engine, identifier, fake)
    assert (
        result["status"] == "IN_PROGRESS"
        and result["outcome_unknown"]
        and not result["automatic_retry"]
        and fake.calls == 1
    )
    engine.dispose()


def test_bounded_feed_pagination_concurrent_read_and_reference_latency(api, pg_settings):
    """Synthetic historical events, not 200 real merchant messages or capacity SLA."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    from local_shop.communication_models import NoticeRead
    from local_shop.models import RecordEvent

    token = setup_customer(api)
    row = customer_record(api, token)
    customer = UUID(
        api[0].get("/api/v1/dev/me", headers={"Authorization": "Bearer " + token}).json()["user_id"]
    )
    engine = build_engine(pg_settings)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                RecordEvent(
                    tenant_id=UUID(A),
                    reservation_id=UUID(row["id"]),
                    actor_id=customer,
                    version=n,
                    from_status="CONFIRMED",
                    to_status="CONFIRMED",
                    action="CONFIRMATION_PROPOSED",
                    note="synthetic bounded history",
                )
                for n in range(2, 201)
            ]
        )
    begin = time.perf_counter()
    first = updates(api)
    elapsed = (time.perf_counter() - begin) * 1000
    assert first["total"] == first["unread"] == 200 and len(first["items"]) == 50
    seen = {x["event_key"] for x in first["items"]}
    for page in range(2, 5):
        result = api[0].get(base() + f"/updates?page={page}", headers=headers(api))
        assert result.status_code == 200
        keys = {x["event_key"] for x in result.json()["items"]}
        assert not seen.intersection(keys)
        seen.update(keys)
    assert len(seen) == 200
    key = first["items"][0]["event_key"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: mark(api, [key]).status_code, range(2)))
    assert results == [200, 200]
    assert updates(api)["unread"] == 199
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(NoticeRead)) == 1
    assert api[0].get(base() + "/updates?page=10001", headers=headers(api)).status_code == 422
    print(f"G_REFERENCE_200_EVENTS_FIRST_PAGE_MS={elapsed:.2f}; NOT_PRODUCTION_SLA")
    engine.dispose()
