import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from local_shop.access import build_access
from local_shop.catalog import published_store
from local_shop.db import build_engine
from local_shop.identity import DEMO_USERS
from local_shop.models import (
    PlatformAdmin,
    PlatformOperation,
    ShopInvitation,
    Tenant,
    TenantMember,
    User,
)
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_customers_integration import A, B, base, create, headers
from test_customers_integration import client as client

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)


@pytest.fixture
def platform(client):
    client.tokens["platform-admin"] = client.post(
        "/api/v1/dev/session", json={"identity": "platform-admin"}
    ).json()["access_token"]
    return client


def invite(client, key=None, **extra):
    return client.post(
        "/api/v1/platform/invitations",
        headers=headers(client, "platform-admin", key),
        json={
            "owner_user_id": DEMO_USERS["customer-a"],
            "proposed_name": "合成试用店",
            "reason": "合成邀请审核",
            **extra,
        },
    )


def respond(client, row, alias="customer-a", **extra):
    return client.post(
        f"/api/v1/me/shop-invitations/{row['id']}/response",
        headers=headers(client, alias),
        json={"expected_version": row["version"], "decision": "ACCEPTED", **extra},
    )


def review(client, row, key=None, **extra):
    return client.post(
        f"/api/v1/platform/invitations/{row['id']}/review",
        headers=headers(client, "platform-admin", key),
        json={
            "expected_version": row["version"],
            "decision": "APPROVED",
            "reason": "合成资质人工复核",
            **extra,
        },
    )


def status(client, tenant=A, key=None, **extra):
    return client.post(
        f"/api/v1/platform/tenants/{tenant}/status",
        headers=headers(client, "platform-admin", key),
        json={"expected_version": 1, "status": "SUSPENDED", "reason": "合成异常处理", **extra},
    )


def test_platform_role_is_separate_and_never_grants_customer_record_access(platform):
    for alias in ["customer-a", "merchant-a", "merchant-b"]:
        for path in ["me", "tenants", "invitations", "audit"]:
            assert (
                platform.get(
                    "/api/v1/platform/" + path, headers=headers(platform, alias)
                ).status_code
                == 403
            )
        assert (
            platform.post(
                "/api/v1/platform/invitations",
                headers=headers(platform, alias),
                json={"owner_user_id": DEMO_USERS[alias], "proposed_name": "x", "reason": "x"},
            ).status_code
            == 403
        )
    row = create(platform).json()
    assert (
        platform.get(
            base() + f"/reservations/{row['id']}", headers=headers(platform, "platform-admin")
        ).status_code
        == 404
    )
    assert (
        platform.get(
            "/api/v1/me/records/reservation/" + row["id"],
            headers=headers(platform, "platform-admin"),
        ).status_code
        == 404
    )
    assert (
        platform.get(
            "/api/v1/merchant/tenants", headers=headers(platform, "platform-admin")
        ).json()["items"]
        == []
    )


def test_invitation_requires_recipient_then_review_and_starts_unpublished(platform, pg_settings):
    row = invite(platform).json()
    assert row["status"] == "INVITED" and row["tenant_id"] is None
    assert review(platform, row).status_code == 409
    assert platform.get("/api/v1/merchant/tenants", headers=headers(platform)).json()["items"] == []
    accepted = respond(platform, row).json()
    assert accepted["status"] == "ACCEPTED" and "owner_user_id" not in accepted
    approved = review(platform, accepted).json()
    assert approved["status"] == "APPROVED" and approved["tenant_id"]
    tid = approved["tenant_id"]
    members = platform.get("/api/v1/merchant/tenants", headers=headers(platform)).json()["items"]
    assert members == [{"id": tid, "name": "合成试用店", "role": "OWNER"}]
    store = platform.get(base(tid) + "/store", headers=headers(platform)).json()
    assert store["published"] is False and store["allow_pickup"] is False
    assert platform.get(f"/api/v1/stores/{tid}").status_code == 404
    assert (
        platform.get(base(tid) + "/store", headers=headers(platform, "customer-b")).status_code
        == 404
    )
    audit = platform.get(
        "/api/v1/platform/audit", headers=headers(platform, "platform-admin")
    ).json()
    assert audit["total"] == 3
    assert all(
        "payload_hash" not in x and "response" not in x and "key" not in x for x in audit["items"]
    )
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Tenant)) == 3
        assert (
            session.get(TenantMember, (UUID(tid), UUID(DEMO_USERS["customer-a"]))).role == "OWNER"
        )
    engine.dispose()


def test_only_invited_verified_account_can_respond_and_list(platform):
    row = invite(platform).json()
    assert respond(platform, row, "customer-b").status_code == 404
    assert respond(platform, row, "merchant-a").status_code == 404
    assert (
        platform.get("/api/v1/me/shop-invitations", headers=headers(platform, "customer-b")).json()[
            "total"
        ]
        == 0
    )
    mine = platform.get("/api/v1/me/shop-invitations", headers=headers(platform)).json()
    assert mine["total"] == 1 and "reason" not in mine["items"][0]
    assert "owner_user_id" not in mine["items"][0]
    assert (
        platform.post(
            f"/api/v1/me/shop-invitations/{row['id']}/response",
            headers=headers(platform),
            json={
                "expected_version": 1,
                "decision": "ACCEPTED",
                "owner_user_id": DEMO_USERS["customer-b"],
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("decision", ["DECLINED", "REJECTED"])
def test_declined_or_rejected_invitation_cannot_be_approved(platform, decision):
    row = invite(platform).json()
    closed = (
        respond(platform, row, decision=decision)
        if decision == "DECLINED"
        else review(platform, row, decision=decision)
    )
    assert closed.status_code == 200 and closed.json()["status"] == decision
    assert review(platform, closed.json()).status_code == 409
    assert respond(platform, closed.json()).status_code == 409


def test_same_platform_key_replays_original_but_mismatch_and_cross_action_fail(platform):
    key = str(uuid4())
    row = invite(platform, key).json()
    assert invite(platform, key).json() == row
    assert invite(platform, key, proposed_name="different").status_code == 409
    assert status(platform, key=key).status_code == 409
    approved = review(platform, respond(platform, row).json()).json()
    assert (
        invite(platform, key).json() == row
    )  # Idempotent response is original, not current status.
    assert approved["tenant_id"]


def test_concurrent_same_invitation_key_creates_one_record_and_audit(platform):
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=5) as pool:
        replies = list(pool.map(lambda _: invite(platform, key), range(5)))
    assert all(x.status_code == 201 for x in replies)
    assert len({x.json()["id"] for x in replies}) == 1
    assert (
        platform.get("/api/v1/platform/audit", headers=headers(platform, "platform-admin")).json()[
            "total"
        ]
        == 1
    )


def test_concurrent_review_creates_only_one_tenant(platform, pg_settings):
    row = respond(platform, invite(platform).json()).json()
    with ThreadPoolExecutor(max_workers=5) as pool:
        replies = list(pool.map(lambda _: review(platform, row), range(5)))
    assert sorted(x.status_code for x in replies) == [200, 409, 409, 409, 409]
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Tenant)) == 3
        assert session.scalar(select(func.count()).select_from(PlatformOperation)) == 3
    engine.dispose()


def test_suspend_hides_public_and_blocks_merchant_but_preserves_customer_history(platform):
    row = create(platform).json()
    key = str(uuid4())
    suspended = status(platform, key=key)
    assert suspended.status_code == 200 and suspended.json()["version"] == 2
    assert status(platform, key=key).json() == suspended.json()
    assert platform.get(f"/api/v1/stores/{A}").status_code == 404
    assert create(platform).status_code == 404
    assert (
        platform.get(base() + "/reservations", headers=headers(platform, "merchant-a")).status_code
        == 404
    )
    assert (
        platform.post(
            base() + "/reservations",
            headers=headers(platform, "merchant-a"),
            json={"customer_label": "合成", "raw_text": "合成"},
        ).status_code
        == 404
    )
    assert (
        platform.get(
            "/api/v1/me/records/reservation/" + row["id"], headers=headers(platform)
        ).status_code
        == 200
    )
    assert platform.get(f"/api/v1/stores/{B}").status_code == 200
    assert status(platform, status="ACTIVE").status_code == 409
    assert status(platform, expected_version=2, status="ACTIVE").status_code == 200
    assert platform.get(f"/api/v1/stores/{A}").status_code == 200
    assert (
        platform.get(
            base() + f"/reservations/{row['id']}", headers=headers(platform, "merchant-a")
        ).status_code
        == 200
    )


def test_concurrent_status_changes_apply_once(platform):
    with ThreadPoolExecutor(max_workers=5) as pool:
        replies = list(pool.map(lambda _: status(platform), range(5)))
    assert sorted(x.status_code for x in replies) == [200, 409, 409, 409, 409]


def test_disabled_admin_and_owner_are_checked_at_each_command(platform, pg_settings):
    row = respond(platform, invite(platform).json()).json()
    engine = build_engine(pg_settings)
    with Session(engine) as session, session.begin():
        session.get(User, UUID(DEMO_USERS["customer-a"])).status = "DISABLED"
    assert review(platform, row).json()["code"] == "INVITATION_OWNER_INACTIVE"
    assert invite(platform).status_code == 404
    with Session(engine) as session, session.begin():
        session.get(PlatformAdmin, UUID(DEMO_USERS["platform-admin"])).status = "DISABLED"
    assert status(platform).status_code == 403
    engine.dispose()


def test_platform_commit_failure_rolls_back_tenant_member_invitation_and_audit(
    platform, pg_settings
):
    row = respond(platform, invite(platform).json()).json()

    def fail(session):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        assert review(platform, row).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Tenant)) == 2
        assert session.scalar(select(func.count()).select_from(TenantMember)) == 2
        assert session.scalar(select(func.count()).select_from(PlatformOperation)) == 2
        assert session.get(ShopInvitation, UUID(row["id"])).status == "ACCEPTED"
    engine.dispose()
    assert review(platform, row).status_code == 200


@pytest.mark.parametrize("access_path", ["merchant", "customer"])
def test_business_authorization_holds_tenant_share_lock_until_transaction_finishes(
    platform, pg_settings, access_path
):
    engine = build_engine(pg_settings)
    with Session(engine) as existing, existing.begin():
        if access_path == "merchant":
            build_access(pg_settings, engine).authorize(
                existing, UUID(A), UUID(DEMO_USERS["merchant-a"])
            )
        else:
            published_store(existing, UUID(A))
        with pytest.raises(SQLAlchemyError):
            with Session(engine) as suspension, suspension.begin():
                suspension.execute(text("SET LOCAL lock_timeout = '100ms'"))
                suspension.execute(
                    text("UPDATE tenants SET status='SUSPENDED' WHERE id=:id"), {"id": A}
                )
    assert status(platform).status_code == 200
    engine.dispose()


@pytest.mark.parametrize(
    "payload", [{"owner_user_id": str(uuid4())}, {"proposed_name": " "}, {"reason": " "}]
)
def test_invalid_platform_input_does_not_create_partial_invitation(platform, payload):
    response = invite(platform, **payload)
    assert response.status_code in {404, 422}
    assert (
        platform.get(
            "/api/v1/platform/invitations", headers=headers(platform, "platform-admin")
        ).json()["total"]
        == 0
    )


def test_downgrade_refuses_to_destroy_platform_history(platform, pg_settings):
    from conftest import migrate

    invite(platform)
    with pytest.raises(AssertionError, match="Migration failed"):
        migrate(pg_settings, "downgrade", "0008_confirmations")
    assert "0011_verified_identity" in migrate(pg_settings, "current").stdout
    assert (
        platform.get(
            "/api/v1/platform/invitations", headers=headers(platform, "platform-admin")
        ).json()["total"]
        == 1
    )


def test_platform_role_cannot_read_or_modify_private_customer_attachments(platform):
    from test_private_attachments_integration import own_url, upload_private

    media = upload_private(platform).json()
    row = create(platform, media_ids=[media["id"]]).json()
    assert row["attachments"]
    merchant_url = base() + f"/media/{media['id']}/content"
    assert platform.get(merchant_url, headers=headers(platform, "merchant-a")).status_code == 200
    assert (
        platform.get(merchant_url, headers=headers(platform, "platform-admin")).status_code == 404
    )
    assert (
        platform.get(own_url(media["id"]), headers=headers(platform, "platform-admin")).status_code
        == 404
    )
    assert (
        platform.patch(
            base() + f"/media/{media['id']}",
            headers=headers(platform, "platform-admin"),
            json={"status": "ARCHIVED", "expected_version": 1},
        ).status_code
        == 404
    )
