"""New pilot endpoints with real formal sessions; only provider HTTPS is a test double."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from local_shop.formal_auth import digest
from local_shop.models import AuthSession, TenantMember
from sqlalchemy.orm import Session
from test_formal_identity import A, B, auth, login, real_auth

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
__all__ = ["real_auth"]


def member(context, token, tenant):
    uid = UUID(context[0].get("/api/v1/auth/me", headers=auth(token)).json()["user_id"])
    with Session(context[2]) as session, session.begin():
        session.add(
            TenantMember(tenant_id=UUID(tenant), user_id=uid, role="OWNER", status="ACTIVE")
        )
    return uid


def test_concurrent_browser_confirmation_and_poll_are_single_recipient(real_auth):
    client = real_auth[0]
    tokens = [login(real_auth, "alice_pilot"), login(real_auth, "bob_pilot")]
    users = [member(real_auth, token, tenant) for token, tenant in zip(tokens, [A, B], strict=True)]
    pending = client.post("/api/v1/auth/browser-approvals").json()

    def confirm(token):
        return client.post(
            "/api/v1/auth/browser-approvals/confirm",
            headers=auth(token),
            json={"code": pending["code"], "confirmed": True},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, tokens))
    assert sorted(r.status_code for r in results) == [200, 404]
    winner = [r.status_code for r in results].index(200)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(
            pool.map(
                lambda _: client.post(
                    "/api/v1/auth/browser-approvals/poll", json={"secret": pending["secret"]}
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in claimed) == [200, 401]
    browser = next(r for r in claimed if r.status_code == 200).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=auth(browser)).json()
    assert me["user_id"] == str(users[winner])
    allowed, other = [A, B][winner], [B, A][winner]
    assert (
        client.get(f"/api/v1/merchant/tenants/{allowed}/updates", headers=auth(browser)).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/merchant/tenants/{other}/updates", headers=auth(browser)).status_code
        == 404
    )
    assert pending["secret"] not in str(me) and pending["code"] not in str(me)


@pytest.mark.parametrize("invalid", ["expired", "revoked"])
def test_invalid_formal_session_cannot_read_or_mutate_new_pilot_endpoints(real_auth, invalid):
    from test_media_integration import picture

    client, config, engine, _, _ = real_auth
    token = login(real_auth, "pilot_" + invalid)
    member(real_auth, token, A)
    root = f"/api/v1/merchant/tenants/{A}"
    h = auth(token) | {"Idempotency-Key": str(uuid4())}
    row = client.post(
        root + "/reservations",
        headers=h,
        json={"customer_label": "合成", "raw_text": "合成", "mark_confirmed": True},
    )
    assert row.status_code == 201, row.text
    rid = row.json()["id"]
    image = client.post(
        root + "/private-media",
        headers=auth(token) | {"Idempotency-Key": str(uuid4()), "Content-Type": "image/png"},
        content=picture(),
    )
    assert image.status_code == 201, image.text
    with Session(engine) as session, session.begin():
        value = session.get(AuthSession, digest(config, token))
        if invalid == "expired":
            value.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        else:
            value.revoked = True
    paths = [
        root + "/preparation",
        root + "/catalog-imports",
        root + "/catalog-imports/template",
        root + "/fulfillment",
        root + "/updates",
        root + f"/reservations/{rid}/contacts",
        root + f"/reservations/{rid}/contact-draft",
        root + f"/media/{image.json()['id']}/content",
        f"/api/v1/me/stores/{A}/updates",
    ]
    for path in paths:
        response = client.get(path, headers=auth(token))
        assert response.status_code == 401, (path, response.status_code)
    posts = [
        (root + "/catalog-imports", {"csv_text": "invalid"}),
        (root + "/updates/read", {"event_keys": ["r:" + str(uuid4())]}),
        (
            root + f"/reservations/{rid}/contacts",
            {"method": "PHONE", "note": "", "confirmed": True, "expected_version": 1},
        ),
        (
            root + "/fulfillment/exports",
            {"purpose": "PREPARATION", "format": "CSV", "expected_fingerprint": "0" * 64},
        ),
    ]
    for path, body in posts:
        assert client.post(path, headers=h, json=body).status_code == 401, path
    assert client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).status_code == 404
