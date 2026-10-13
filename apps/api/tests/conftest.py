"""Real PostgreSQL tests. Explicit opt-in creates/drops only a unique synthetic test database."""

import os
import secrets
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from local_shop.config import Settings
from local_shop.seed import seed
from psycopg import sql

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="Real PostgreSQL admin URL not configured")
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def pg_settings(tmp_path):
    name = "local_shop_test_" + uuid4().hex
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    from sqlalchemy.engine import make_url

    db = make_url(ADMIN_URL).set(drivername="postgresql+psycopg", database=name)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=db.render_as_string(hide_password=False),
        app_secret_key=secrets.token_urlsafe(32),
        dev_auth_enabled=True,
        media_root=tmp_path / "media",
    )
    migrate(settings, "upgrade", "head")
    seed(settings)
    yield settings
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def migrate(settings, *args):
    env = os.environ | {
        "APP_ENV": "test",
        "DATABASE_URL": settings.database_url.get_secret_value(),
        "APP_SECRET_KEY": settings.app_secret_key.get_secret_value(),
        "DEV_AUTH_ENABLED": "false",
    }
    result = subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "-c", "apps/api/alembic.ini", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "Migration failed; inspect protected local logs"
    return result
