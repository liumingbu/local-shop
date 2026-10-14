import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "patch,reason",
    [
        ({}, "BLOCKED_REAL_WECHAT_ACCEPTANCE"),
        ({"APP_ENV": "test"}, "BLOCKED_ENVIRONMENT"),
        ({"DEV_AUTH_ENABLED": "true"}, "BLOCKED_CONFIGURATION"),
        ({"API_HOST": "0.0.0.0"}, "BLOCKED_BINDING"),
        ({"DATABASE_URL": ""}, "BLOCKED_CONFIGURATION"),
        ({"APP_SECRET_KEY": "short"}, "BLOCKED_CONFIGURATION"),
    ],
)
def test_release_gate_never_blesses_current_development_build(tmp_path, patch, reason):
    key = secrets.token_urlsafe(32)
    env = os.environ | {
        "APP_ENV": "production",
        "DEV_AUTH_ENABLED": "false",
        "WECHAT_LOGIN_ENABLED": "true",
        "WECHAT_APPID": "wx0000000000000000",
        "WECHAT_APP_SECRET": "SYNTHETIC-PREFLIGHT-ONLY",
        "API_HOST": "127.0.0.1",
        "APP_SECRET_KEY": key,
        "DATABASE_URL": "postgresql+psycopg://synthetic:private-placeholder@localhost/unused",
        **patch,
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/production_preflight.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and reason in result.stdout
    assert key not in result.stdout + result.stderr
    assert "private-placeholder" not in result.stdout + result.stderr


def test_service_template_requires_release_gate_and_does_not_embed_credentials():
    unit = (ROOT / "infra/systemd/local-shop-api.service.template").read_text()
    assert "ExecStartPre=" in unit and "production_preflight.py" in unit
    assert "EnvironmentFile=@@ENV_FILE@@" in unit
    assert "UMask=0077" in unit and "NoNewPrivileges=true" in unit
    assert "APP_SECRET_KEY=" not in unit and "DATABASE_URL=" not in unit
