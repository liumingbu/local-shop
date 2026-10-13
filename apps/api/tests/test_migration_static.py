import os
import secrets
import subprocess
from pathlib import Path

from local_shop.models import Base
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def test_postgresql_model_constraints_compile():
    assert {"users", "tenants", "tenant_members"}.issubset(Base.metadata.tables)
    sql = "\n".join(
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in Base.metadata.sorted_tables
    )
    assert "UUID" in sql
    assert "PRIMARY KEY (tenant_id, user_id)" in sql
    assert "FOREIGN KEY(tenant_id)" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql


def test_alembic_offline_sql():
    root = Path(__file__).resolve().parents[3]
    env = os.environ | {
        "DATABASE_URL": "postgresql+psycopg://synthetic@localhost/example",
        "APP_SECRET_KEY": secrets.token_urlsafe(32),
        "DEV_AUTH_ENABLED": "false",
    }
    result = subprocess.run(
        [str(root / ".venv/bin/alembic"), "-c", "apps/api/alembic.ini", "upgrade", "head", "--sql"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE tenant_members" in result.stdout
    assert "0001_identity" in result.stdout
