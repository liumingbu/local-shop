"""Real PostgreSQL tests. Explicit opt-in creates/drops only a unique synthetic test database."""

import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from conftest import migrate
from fastapi.testclient import TestClient
from local_shop.db import build_engine
from local_shop.main import create_app
from local_shop.models import Tenant, TenantMember, User
from local_shop.seed import seed
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="Real PostgreSQL admin URL not configured")
ROOT = Path(__file__).resolve().parents[3]


def test_real_migration_idempotent(pg_settings):
    migrate(pg_settings, "upgrade", "head")
    assert "0003_catalog" in migrate(pg_settings, "current").stdout


def test_real_seed_idempotent(pg_settings):
    seed(pg_settings)
    seed(pg_settings)
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session:
            for model in (Tenant, User, TenantMember):
                assert session.scalar(select(func.count()).select_from(model)) == 2
    finally:
        engine.dispose()


def test_real_health_readiness(pg_settings):
    with TestClient(create_app(pg_settings)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


def test_real_transaction_rollback(pg_settings):
    engine = build_engine(pg_settings)
    uid = uuid4()
    try:
        with pytest.raises(RuntimeError):
            with Session(engine) as session, session.begin():
                session.add(User(id=uid, identity_type="DEVELOPMENT", display_name="rollback-only"))
                session.flush()
                raise RuntimeError("intentional test rollback")
        with Session(engine) as session:
            assert session.get(User, uid) is None
    finally:
        engine.dispose()


def test_real_foreign_key_and_role_constraints(pg_settings):
    engine = build_engine(pg_settings)
    try:
        with pytest.raises(IntegrityError):
            with Session(engine) as session, session.begin():
                session.add(TenantMember(tenant_id=uuid4(), user_id=uuid4(), role="OWNER"))
                session.flush()
        with pytest.raises(IntegrityError):
            with Session(engine) as session, session.begin():
                session.add(
                    TenantMember(
                        tenant_id=UUID("10000000-0000-4000-8000-000000000001"),
                        user_id=UUID("00000000-0000-4000-8000-000000000002"),
                        role="ADMIN",
                    )
                )
                session.flush()
    finally:
        engine.dispose()


def test_real_seed_refuses_collision(pg_settings):
    engine = build_engine(pg_settings)
    uid = UUID("00000000-0000-4000-8000-000000000001")
    try:
        with Session(engine) as session, session.begin():
            user = session.get(User, uid)
            user.identity_type = "REAL_IDENTITY"
        with pytest.raises(RuntimeError, match="collision"):
            seed(pg_settings)
        with Session(engine) as session, session.begin():
            user = session.get(User, uid)
            assert user.identity_type == "REAL_IDENTITY"
            user.identity_type = "DEVELOPMENT"
    finally:
        engine.dispose()


def test_real_downgrade_and_reupgrade(pg_settings):
    migrate(pg_settings, "downgrade", "base")
    migrate(pg_settings, "upgrade", "head")
    seed(pg_settings)
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Tenant)) == 2
    finally:
        engine.dispose()
