import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from local_shop.db import build_engine
from local_shop.main import create_app
from local_shop.models import MediaObject, Tenant
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from starlette.requests import Request
from test_media_integration import base, headers, picture
from test_media_integration import client as client

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
A = UUID("10000000-0000-4000-8000-000000000001")


def test_database_statement_deadline_and_recovery(pg_settings):
    pg_settings.db_statement_timeout_ms = 100
    engine = build_engine(pg_settings)
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("SHOW statement_timeout")) == "100ms"
            assert conn.scalar(text("SHOW lock_timeout")) == "3s"
            with pytest.raises(DBAPIError) as caught:
                conn.execute(text("SELECT pg_sleep(1)"))
            assert caught.value.orig.sqlstate == "57014"
            conn.rollback()
            assert conn.scalar(text("SELECT 42")) == 42
    finally:
        engine.dispose()


def test_database_lock_deadline_does_not_change_locked_data(pg_settings):
    pg_settings.db_lock_timeout_ms = 100
    engine = build_engine(pg_settings)
    try:
        with engine.connect() as holder, engine.connect() as contender:
            holder.execute(text("SELECT id FROM tenants WHERE id=:id FOR UPDATE"), {"id": A})
            with pytest.raises(DBAPIError) as caught:
                contender.execute(
                    text("UPDATE tenants SET status='SUSPENDED' WHERE id=:id"), {"id": A}
                )
            assert caught.value.orig.sqlstate == "55P03"
            contender.rollback()
            holder.rollback()
            assert (
                contender.scalar(text("SELECT status FROM tenants WHERE id=:id"), {"id": A})
                == "ACTIVE"
            )
    finally:
        engine.dispose()


def test_upload_timeout_rolls_back_and_releases_tenant_lock(pg_settings, monkeypatch):
    import asyncio

    pg_settings.media_receive_timeout_seconds = 0.05
    app = create_app(pg_settings)
    original = Request.stream

    async def slow(self):
        if self.url.path.endswith("/media"):
            await asyncio.sleep(1)
        async for chunk in original(self):
            yield chunk

    engine = build_engine(pg_settings)
    try:
        with TestClient(app, client=("127.0.0.1", 50001)) as client:
            client.tokens = {
                "merchant-a": client.post(
                    "/api/v1/dev/session", json={"identity": "merchant-a"}
                ).json()["access_token"]
            }
            monkeypatch.setattr(Request, "stream", slow)
            response = client.post(
                base() + "/media",
                headers=headers(client, key="bounded-rollback") | {"Content-Type": "image/png"},
                content=picture(),
            )
            assert response.status_code == 408 and response.json()["code"] == "IMAGE_UPLOAD_TIMEOUT"
            with Session(engine) as session, session.begin():
                assert session.scalar(select(func.count()).select_from(MediaObject)) == 0
                assert (
                    session.scalar(
                        select(Tenant).where(Tenant.id == A).with_for_update(nowait=True)
                    )
                    is not None
                )
            assert not pg_settings.media_root.exists()
            monkeypatch.setattr(Request, "stream", original)
            response = client.post(
                base() + "/media",
                headers=headers(client, key="bounded-rollback") | {"Content-Type": "image/png"},
                content=picture(),
            )
            assert response.status_code == 201
    finally:
        engine.dispose()


def test_pool_wait_is_bounded_and_recovers_after_release(pg_settings):
    import time

    from sqlalchemy.exc import TimeoutError

    pg_settings.db_pool_timeout_seconds = 0.05
    engine = build_engine(pg_settings)
    connections = []
    try:
        # SQLAlchemy default pool: 5 retained + 10 overflow connections.
        connections = [engine.connect() for _ in range(15)]
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            engine.connect()
        assert time.monotonic() - started < 1
        connections.pop().close()
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT 1")) == 1
    finally:
        for conn in connections:
            conn.close()
        engine.dispose()


def test_actual_database_timeout_response_redacts_sql(pg_settings, monkeypatch):
    pg_settings.db_statement_timeout_ms = 100

    def slow(engine):
        with engine.connect() as connection:
            connection.execute(text("SELECT pg_sleep(1) /* synthetic-private-sql */"))

    monkeypatch.setattr("local_shop.main.probe_database", slow)
    with TestClient(create_app(pg_settings)) as client:
        result = client.get("/health/ready")
        assert result.status_code == 503
        assert result.json()["code"] == "DATABASE_UNAVAILABLE"
        assert "synthetic-private-sql" not in result.text and "pg_sleep" not in result.text
        assert result.headers["X-Request-ID"]
