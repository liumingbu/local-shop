"""Only the external HTTPS provider is mocked; identity/session/tenant state uses real PG."""

import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from local_shop import wechat_login
from local_shop.config import Settings
from local_shop.db import build_engine
from local_shop.formal_auth import digest
from local_shop.main import create_app
from local_shop.models import AuthSession, PlatformAdmin, TenantMember, User, WeChatIdentity
from sqlalchemy import func, select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"


@pytest.fixture
def real_auth(pg_settings, monkeypatch):
    config = Settings(
        **(
            pg_settings.model_dump()
            | {
                "dev_auth_enabled": False,
                "wechat_login_enabled": True,
                "wechat_appid": "wx0000000000000000",
                "wechat_app_secret": "SYNTHETIC-NOT-A-REAL-SECRET",
            }
        )
    )
    calls = []
    provider = {
        "handler": lambda code: {
            "openid": "synthetic-" + code.split("_")[0],
            "session_key": base64.b64encode(b"synthetic-key-16").decode(),
        }
    }
    # exactly 16 bytes; this is never a real credential.
    provider["handler"] = lambda code: {
        "openid": "synthetic-" + code.split("_")[0],
        "session_key": base64.b64encode(b"0123456789abcdef").decode(),
    }

    class Response:
        status = 200

        def __init__(self, value):
            self.body = json.dumps(value).encode()

        def read1(self, size):
            part, self.body = self.body[:size], self.body[size:]
            return part

    class Connection:
        def __init__(self, host, timeout, context):
            assert (
                host == "api.weixin.qq.com" and context.check_hostname and context.verify_mode == 2
            )
            self.sock = self

        def set_debuglevel(self, value):
            assert value == 0

        def settimeout(self, value):
            assert 0 < value <= 5

        def request(self, method, path, headers):
            assert method == "GET" and urlsplit(path).path == "/sns/jscode2session"
            query = parse_qs(urlsplit(path).query)
            assert query["grant_type"] == ["authorization_code"]
            assert query["appid"] == [config.wechat_appid]
            calls.append(query["js_code"][0])
            self.value = provider["handler"](query["js_code"][0])

        def getresponse(self):
            return Response(self.value)

        def close(self):
            pass

    monkeypatch.setattr(wechat_login.http.client, "HTTPSConnection", Connection)
    engine = build_engine(config)
    with TestClient(create_app(config), client=("127.0.0.1", 55101)) as client:
        yield client, config, engine, calls, provider
    engine.dispose()


def login(context, code="alice_first"):
    result = context[0].post("/api/v1/auth/wechat/session", json={"code": code})
    assert result.status_code == 200, result.text
    return result.json()["access_token"]


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_provider_mapping_opaque_revocable_sessions_and_replay(real_auth, caplog):
    client, config, engine, calls, _ = real_auth
    token = login(real_auth)
    me = client.get("/api/v1/auth/me", headers=auth(token)).json()
    assert me["development_only"] is False and me["account_code"].startswith("U-")
    again = login(real_auth, "alice_second")
    assert again != token
    assert client.get("/api/v1/auth/me", headers=auth(again)).json() == me
    assert (
        client.post("/api/v1/auth/wechat/session", json={"code": "alice_first"}).status_code == 401
    )
    assert len(calls) == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WeChatIdentity)) == 1
        assert session.get(AuthSession, token) is None
        assert session.get(AuthSession, digest(config, token)).user_id == UUID(me["user_id"])
    assert not any(
        value in json.dumps(me) + caplog.text
        for value in [
            token,
            "session_key",
            config.wechat_app_secret.get_secret_value(),
            "synthetic-alice",
        ]
    )
    assert client.post("/api/v1/auth/logout", headers=auth(token)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth(again)).status_code == 200


def test_client_cannot_supply_identity_role_or_tenant_and_demo_cannot_enter(real_auth, pg_settings):
    from local_shop.identity import issue_demo_token

    client = real_auth[0]
    for extra in [
        {"openid": "victim"},
        {"role": "PLATFORM_ADMIN"},
        {"tenant_id": A},
        {"user_id": A},
    ]:
        assert (
            client.post(
                "/api/v1/auth/wechat/session", json={"code": "alice_x", **extra}
            ).status_code
            == 422
        )
    assert (
        client.post("/api/v1/dev/session", json={"identity": "platform-admin"}).status_code == 404
    )
    assert (
        client.get(
            "/api/v1/platform/me", headers=auth(issue_demo_token("platform-admin", pg_settings))
        ).status_code
        == 401
    )
    token = login(real_auth)
    assert client.get("/api/v1/platform/me", headers=auth(token)).status_code == 403
    assert (
        client.get(f"/api/v1/merchant/tenants/{A}/reservations", headers=auth(token)).status_code
        == 404
    )


@pytest.mark.parametrize(
    "failure",
    [
        {"errcode": 40029},
        {"errcode": 40163},
        {"errcode": 45011},
        {"errcode": -1},
        {"openid": "x"},
        {"openid": "x", "session_key": "bad"},
        [],
    ],
)
def test_provider_failures_create_no_identity_or_session(real_auth, failure):
    client, _, engine, _, provider = real_auth
    provider["handler"] = lambda _: failure
    for code in ("invalid", "invalid"):
        assert client.post("/api/v1/auth/wechat/session", json={"code": code}).status_code in (
            401,
            429,
            503,
        )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WeChatIdentity)) == 0
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_provider_timeout_and_missing_config_fail_closed(real_auth, pg_settings):
    client, _, _, _, provider = real_auth

    def timeout(_):
        raise TimeoutError("synthetic external timeout")

    provider["handler"] = timeout
    assert client.post("/api/v1/auth/wechat/session", json={"code": "timeout"}).status_code == 503
    with TestClient(create_app(pg_settings), client=("127.0.0.1", 55102)) as disabled:
        assert (
            disabled.post("/api/v1/auth/wechat/session", json={"code": "anything"}).status_code
            == 503
        )
        assert disabled.post("/api/v1/auth/browser-approvals").status_code == 503


def test_concurrent_first_login_same_mapping_and_replayed_code(real_auth):
    client = real_auth[0]

    def post(code):
        return client.post("/api/v1/auth/wechat/session", json={"code": code})

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(post, ["alice_1", "alice_2", "alice_3", "alice_3"]))
    assert sorted(x.status_code for x in results) == [200, 200, 200, 401]
    users = {
        client.get("/api/v1/auth/me", headers=auth(x.json()["access_token"])).json()["user_id"]
        for x in results
        if x.status_code == 200
    }
    assert len(users) == 1


def test_expiration_disabled_and_real_tenant_scope(real_auth):
    client, config, engine, _, _ = real_auth
    token = login(real_auth)
    uid = UUID(client.get("/api/v1/auth/me", headers=auth(token)).json()["user_id"])
    with Session(engine) as session, session.begin():
        session.add(TenantMember(tenant_id=UUID(A), user_id=uid, role="OWNER", status="ACTIVE"))
    assert (
        client.get(f"/api/v1/merchant/tenants/{A}/reservations", headers=auth(token)).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/merchant/tenants/{B}/reservations", headers=auth(token)).status_code
        == 404
    )
    with Session(engine) as session, session.begin():
        session.get(AuthSession, digest(config, token)).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    token = login(real_auth, "alice_fresh")
    with Session(engine) as session, session.begin():
        session.get(User, uid).status = "DISABLED"
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    assert (
        client.post("/api/v1/auth/wechat/session", json={"code": "alice_disabled"}).status_code
        == 401
    )


def test_browser_approval_requires_verified_explicit_identity_consumes_once_and_checks_roles(
    real_auth,
):
    client, config, engine, _, _ = real_auth
    token = login(real_auth)
    uid = UUID(client.get("/api/v1/auth/me", headers=auth(token)).json()["user_id"])
    with Session(engine) as session, session.begin():
        session.add(PlatformAdmin(user_id=uid, status="ACTIVE"))
    pending = client.post("/api/v1/auth/browser-approvals").json()
    assert (
        client.post(
            "/api/v1/auth/browser-approvals/poll", json={"secret": pending["secret"]}
        ).json()["status"]
        == "PENDING"
    )
    assert (
        client.post(
            "/api/v1/auth/browser-approvals/confirm",
            headers=auth(token),
            json={"code": pending["code"], "confirmed": False},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/browser-approvals/confirm",
            headers=auth(token),
            json={"code": pending["code"], "confirmed": True},
        ).status_code
        == 200
    )
    result = client.post("/api/v1/auth/browser-approvals/poll", json={"secret": pending["secret"]})
    assert result.status_code == 200, result.text
    browser = result.json()["access_token"]
    assert client.get("/api/v1/platform/me", headers=auth(browser)).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/browser-approvals/poll", json={"secret": pending["secret"]}
        ).status_code
        == 401
    )
    assert (
        client.get(f"/api/v1/merchant/tenants/{A}/reservations", headers=auth(browser)).status_code
        == 404
    )
    with Session(engine) as session, session.begin():
        session.get(PlatformAdmin, uid).status = "DISABLED"
    assert client.get("/api/v1/platform/me", headers=auth(browser)).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=auth(browser)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth(browser)).status_code == 401


def test_browser_expiry_foreign_secret_and_account_code_invitation(real_auth):
    from local_shop.models import BrowserApproval

    client, config, engine, _, _ = real_auth
    administrator = login(real_auth, "admin_first")
    owner = login(real_auth, "owner_first")
    admin_id = UUID(client.get("/api/v1/auth/me", headers=auth(administrator)).json()["user_id"])
    code = client.get("/api/v1/auth/me", headers=auth(owner)).json()["account_code"]
    with Session(engine) as session, session.begin():
        session.add(PlatformAdmin(user_id=admin_id, status="ACTIVE"))
    result = client.post(
        "/api/v1/platform/invitations",
        headers={**auth(administrator), "Idempotency-Key": "synthetic-invite-001"},
        json={"owner_account_code": code, "proposed_name": "合成正式身份店", "reason": "合成验证"},
    )
    assert result.status_code == 201, result.text
    mine = client.get("/api/v1/me/shop-invitations", headers=auth(owner))
    assert result.json()["id"] in mine.text
    assert (
        result.json()["id"]
        not in client.get("/api/v1/me/shop-invitations", headers=auth(administrator)).text
    )
    assert (
        client.post(
            "/api/v1/platform/invitations",
            headers={**auth(administrator), "Idempotency-Key": "synthetic-invite-002"},
            json={
                "owner_user_id": "00000000-0000-4000-8000-000000000001",
                "proposed_name": "不允许提升演示账号",
                "reason": "边界",
            },
        ).status_code
        == 404
    )
    pending = client.post("/api/v1/auth/browser-approvals").json()
    assert (
        client.post("/api/v1/auth/browser-approvals/poll", json={"secret": "x" * 43}).status_code
        == 401
    )
    with Session(engine) as session, session.begin():
        session.get(BrowserApproval, digest(config, pending["secret"])).expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
    assert (
        client.post(
            "/api/v1/auth/browser-approvals/poll", json={"secret": pending["secret"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/browser-approvals/confirm",
            headers=auth(owner),
            json={"code": pending["code"], "confirmed": True},
        ).status_code
        == 404
    )


def test_formal_vue_login_over_real_http_and_postgres(real_auth):
    import socket
    import subprocess
    import threading
    import time
    from pathlib import Path

    import httpx
    import uvicorn

    client, _, engine, _, _ = real_auth
    token = login(real_auth, "alice_setup")
    uid = UUID(client.get("/api/v1/auth/me", headers=auth(token)).json()["user_id"])
    with Session(engine) as session, session.begin():
        session.add(PlatformAdmin(user_id=uid, status="ACTIVE"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            client.app, host="127.0.0.1", port=port, log_level="warning", access_log=False
        )
    )
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    root = Path(__file__).resolve().parents[3]
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        assert (
            httpx.get(f"http://127.0.0.1:{port}/health/ready", trust_env=False).status_code == 200
        )
        result = subprocess.run(
            ["npm", "run", "test:dom:formal"],
            cwd=root,
            env=os.environ | {"LOCAL_SHOP_TEST_API": f"http://127.0.0.1:{port}"},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
        print(
            "PASS formal Vue DOM + real HTTP/PG; external provider only mocked; NOT browser/WeChat"
        )
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()
        assert not worker.is_alive()


def test_appid_is_part_of_identity_and_session_scope(real_auth):
    client, config, _, _, _ = real_auth
    first = login(real_auth, "alice_app1")
    old = client.get("/api/v1/auth/me", headers=auth(first)).json()["user_id"]
    config.wechat_appid = "wx1111111111111111"
    assert client.get("/api/v1/auth/me", headers=auth(first)).status_code == 401
    second = login(real_auth, "alice_app2")
    assert client.get("/api/v1/auth/me", headers=auth(second)).json()["user_id"] != old


def test_failed_login_rate_counts_commit_independently(real_auth):
    from types import SimpleNamespace

    from fastapi import HTTPException
    from local_shop.formal_auth import limit

    _, config, engine, _, _ = real_auth
    request = SimpleNamespace(client=SimpleNamespace(host="synthetic-client"))
    limit(engine, config, request, "synthetic-rate", maximum=2)
    limit(engine, config, request, "synthetic-rate", maximum=2)
    with pytest.raises(HTTPException) as failure:
        limit(engine, config, request, "synthetic-rate", maximum=2)
    assert failure.value.status_code == 429


def test_real_identity_tenant_detail_mutation_private_media_and_copy_isolation(real_auth):
    from io import BytesIO
    from uuid import uuid4

    from PIL import Image

    client, _, engine, _, _ = real_auth
    alice = login(real_auth, "alice_owner")
    bob = login(real_auth, "bob_owner")
    a_uid = UUID(client.get("/api/v1/auth/me", headers=auth(alice)).json()["user_id"])
    b_uid = UUID(client.get("/api/v1/auth/me", headers=auth(bob)).json()["user_id"])
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                TenantMember(tenant_id=UUID(A), user_id=a_uid, role="OWNER", status="ACTIVE"),
                TenantMember(tenant_id=UUID(B), user_id=b_uid, role="OWNER", status="ACTIVE"),
            ]
        )
    image = BytesIO()
    Image.new("RGB", (3, 3), "green").save(image, format="PNG")
    result = client.post(
        f"/api/v1/merchant/tenants/{A}/private-media",
        headers={**auth(alice), "Content-Type": "image/png", "Idempotency-Key": str(uuid4())},
        content=image.getvalue(),
    )
    assert result.status_code == 201, result.text
    mid = result.json()["id"]
    result = client.post(
        f"/api/v1/merchant/tenants/{A}/reservations",
        headers={**auth(alice), "Idempotency-Key": str(uuid4())},
        json={
            "customer_label": "合成正式代记",
            "raw_text": "合成私图需求",
            "media_ids": [mid],
            "contact_phone": "SYNTHETIC",
        },
    )
    assert result.status_code == 201, result.text
    row = result.json()
    path = f"/api/v1/merchant/tenants/{A}/reservations/{row['id']}"
    assert client.get(path, headers=auth(alice)).status_code == 200
    for suffix in ("", "/copy-draft"):
        assert client.get(path + suffix, headers=auth(bob)).status_code == 404
    assert (
        client.post(
            path + "/transitions",
            headers={**auth(bob), "Idempotency-Key": str(uuid4())},
            json={"expected_version": row["version"], "target_status": "CONFIRMED"},
        ).status_code
        == 404
    )
    image_path = f"/api/v1/merchant/tenants/{A}/media/{mid}/content"
    assert client.get(image_path, headers=auth(alice)).status_code == 200
    assert client.get(image_path, headers=auth(bob)).status_code == 404
    assert client.get(image_path).status_code == 401
    assert row["id"] not in client.get("/api/v1/me/records", headers=auth(alice)).text
    assert row["id"] not in client.get("/api/v1/me/records", headers=auth(bob)).text
