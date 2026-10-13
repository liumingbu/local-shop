import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from local_shop.config import Settings
from local_shop.main import create_app
from local_shop.seed import seed
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError


@pytest.fixture
def values():
    return dict(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://synthetic@127.0.0.1/local_shop_test",
        app_secret_key=secrets.token_urlsafe(32),
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"app_secret_key": "short"},
        {"app_secret_key": "x" * 40},
        {"database_url": "sqlite:///fake.db"},
        {"database_url": "not-a-url"},
        {"database_url": "postgresql+psycopg://user@localhost"},
        {"app_env": "production", "dev_auth_enabled": True},
        {"api_host": "0.0.0.0", "dev_auth_enabled": True},
        {"api_port": 0},
        {"api_port": 65536},
        {"app_timezone": "invalid/zone"},
        {"app_env": "production"},
    ],
)
def test_invalid_configuration(values, patch):
    with pytest.raises(ValidationError):
        Settings(**(values | patch))


def test_missing_settings(monkeypatch):
    for key in ("DATABASE_URL", "APP_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_repr_hides_secret(values):
    settings = Settings(**values)
    assert values["app_secret_key"] not in repr(settings)
    assert "synthetic@" not in repr(settings)


def test_health_live_without_database(values):
    with TestClient(create_app(Settings(**values))) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["X-Request-ID"]
        assert response.headers["Cache-Control"] == "no-store"
        assert (
            client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).status_code == 404
        )


def test_readiness_error_redacts_internal_details(values, monkeypatch):
    def failure(engine):
        raise OperationalError("SECRET SQL", {}, Exception("SECRET PASSWORD"))

    monkeypatch.setattr("local_shop.main.probe_database", failure)
    with TestClient(create_app(Settings(**values))) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_UNAVAILABLE"
        assert "SECRET" not in response.text


def test_readiness_success_with_explicit_stub(values, monkeypatch):
    # Unit contract only; does not prove PostgreSQL is running.
    monkeypatch.setattr("local_shop.main.probe_database", lambda engine: None)
    with TestClient(create_app(Settings(**values))) as client:
        assert client.get("/health/ready").json() == {"status": "ready"}


def test_demo_sessions_and_identity(values):
    settings = Settings(**(values | {"dev_auth_enabled": True}))
    with TestClient(create_app(settings), client=("127.0.0.1", 50001)) as client:
        users = []
        for alias in ("merchant-a", "merchant-b"):
            response = client.post("/api/v1/dev/session", json={"identity": alias})
            assert response.status_code == 200
            token = response.json()["access_token"]
            me = client.get("/api/v1/dev/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            users.append(me.json()["user_id"])
        assert users[0] != users[1]
        assert client.get("/api/v1/dev/me").status_code == 401
        assert (
            client.get("/api/v1/dev/me", headers={"Authorization": "Bearer garbage"}).status_code
            == 401
        )
        bad = client.post("/api/v1/dev/session", json={"identity": "arbitrary-admin"})
        assert bad.status_code == 422
        assert "arbitrary-admin" not in bad.text


def test_demo_remote_peer_rejected(values):
    app = create_app(Settings(**(values | {"dev_auth_enabled": True})))
    with TestClient(app, client=("192.0.2.1", 50001)) as client:
        assert (
            client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).status_code == 403
        )
        assert client.get("/api/v1/dev/me").status_code == 403


@pytest.mark.parametrize("kind", ["expired", "wrong-audience", "wrong-key", "wrong-subject"])
def test_invalid_tokens(values, kind):
    settings = Settings(**(values | {"dev_auth_enabled": True}))
    now = datetime.now(UTC)
    claims = {
        "sub": "00000000-0000-4000-8000-000000000001",
        "kind": "development",
        "iss": "local-shop-dev",
        "aud": "local-shop",
        "iat": now,
        "exp": now + timedelta(minutes=1),
    }
    key = settings.app_secret_key.get_secret_value()
    if kind == "expired":
        claims["exp"] = now - timedelta(minutes=1)
    if kind == "wrong-audience":
        claims["aud"] = "other"
    if kind == "wrong-key":
        key = secrets.token_urlsafe(32)
    if kind == "wrong-subject":
        claims["sub"] = "other"
    token = jwt.encode(claims, key, algorithm="HS256")
    with TestClient(create_app(settings), client=("127.0.0.1", 1)) as client:
        assert (
            client.get("/api/v1/dev/me", headers={"Authorization": f"Bearer {token}"}).status_code
            == 401
        )


def test_production_has_no_demo_routes(values):
    settings = Settings(
        **(
            values
            | {
                "app_env": "production",
                "database_url": "postgresql+psycopg://synthetic:placeholder@localhost/placeholder",
            }
        )
    )
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/v1/dev/session").status_code == 404
        assert client.get("/api/v1/dev/me").status_code == 404


def test_seed_requires_opt_in(values):
    with pytest.raises(RuntimeError, match="explicit development"):
        seed(Settings(**values))
