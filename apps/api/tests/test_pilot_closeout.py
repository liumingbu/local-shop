"""New E-H boundaries only; real PG, no real identity provider or production data."""

import json
import os
from uuid import UUID, uuid4

import pytest
from local_shop.db import build_engine
from local_shop.import_models import CatalogImport
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_records_integration import api, base, headers

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
__all__ = ["api"]


def test_escaped_invalid_unicode_csv_fails_closed_without_job(api, pg_settings):
    response = api[0].post(
        base() + "/catalog-imports",
        headers={**headers(api, key=str(uuid4())), "Content-Type": "application/json"},
        content=json.dumps({"csv_text": "\ud800"}).encode("ascii"),
    )
    assert response.status_code == 422, response.text
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CatalogImport)) == 0
    engine.dispose()


def test_private_file_write_failure_rolls_back_and_same_key_recovers(api, pg_settings, monkeypatch):
    from local_shop import media
    from local_shop.models import MediaObject
    from test_media_integration import picture

    key = str(uuid4())
    payload = picture()
    root = base() + "/private-media"
    h = {**headers(api, key=key), "Content-Type": "image/png"}

    def fail(_):
        raise OSError("synthetic disk sync failure")

    with monkeypatch.context() as patch:
        patch.setattr(media.os, "fsync", fail)
        response = api[0].post(root, headers=h, content=payload)
    assert response.status_code == 503 and response.json()["code"] == "MEDIA_STORAGE_UNAVAILABLE"
    assert list(pg_settings.media_root.glob("*.jpg")) == []
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MediaObject)) == 0
    result = api[0].post(root, headers=h, content=payload)
    assert result.status_code == 201, result.text
    replay = api[0].post(root, headers=h, content=payload)
    assert replay.status_code == 201 and replay.json()["id"] == result.json()["id"]
    assert len(list(pg_settings.media_root.glob("*.jpg"))) == 1
    assert api[0].get("/api/v1/media/" + result.json()["id"]).status_code == 404
    assert api[0].get(base() + "/media/" + result.json()["id"] + "/content").status_code == 401
    assert (
        api[0]
        .get(base() + "/media/" + result.json()["id"] + "/content", headers=headers(api))
        .status_code
        == 200
    )
    engine.dispose()


def test_readonly_maintenance_reports_growth_expiry_uncertainty_and_missing_backup(
    pg_settings, tmp_path
):
    import importlib.util
    from datetime import UTC, datetime
    from pathlib import Path

    from local_shop.communication_models import NotificationAttempt
    from local_shop.models import AuthRateWindow
    from test_records_integration import A

    module_path = Path(__file__).resolve().parents[3] / "scripts/maintenance_check.py"
    spec = importlib.util.spec_from_file_location("pilot_maintenance", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    minute = int(datetime.now(UTC).timestamp()) // 60
    engine = build_engine(pg_settings)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                AuthRateWindow(bucket=f"synthetic:abc:{minute - 5}", count=1),
                AuthRateWindow(bucket=f"synthetic:abc:{minute + 5}", count=1),
                AuthRateWindow(bucket="legacy-unknown", count=1),
            ]
        )
        session.add(
            NotificationAttempt(
                tenant_id=UUID(A),
                recipient_id=UUID("00000000-0000-4000-8000-000000000001"),
                audience="MERCHANT",
                event_key="r:" + str(uuid4()),
                status="IN_PROGRESS",
            )
        )
    result = module.inspect(pg_settings, tmp_path / "absent-backup")
    assert result["expired_rate_window_candidates"] == 1 and result["rate_window_rows"] == 3
    assert result["notification_unknown_or_in_progress"] == 1
    assert result["database_bytes"] > 0 and result["filesystem_free_bytes"] > 0
    assert not result["delete_supported"] and not result["notification_retry_performed"]
    assert result["backup"]["status"] == "INVALID_OR_UNAVAILABLE"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuthRateWindow)) == 3
        assert session.scalar(select(NotificationAttempt.status)) == "IN_PROGRESS"
    engine.dispose()
