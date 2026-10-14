"""Actual SQL statement counts and old successful-key compatibility, not mocked DB."""

import hashlib
import json
import os

import pytest
from local_shop.db import build_engine
from local_shop.models import IdempotencyKey
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_records_integration import api, base, create, headers

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
__all__ = ["api"]


def test_page_relations_do_not_scale_queries_per_row(api):
    for n in range(25):
        assert create(api, raw_text=f"合成分页{n}").status_code == 201
    statements = []

    def before(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(Engine, "before_cursor_execute", before)
    try:
        result = api[0].get(base() + "/reservations?limit=20", headers=headers(api))
        assert result.status_code == 200 and len(result.json()["items"]) == 20
        assert len(statements) <= 8, len(statements)
        assert all(
            {"attachments", "cancellation_requests", "confirmation_revisions"} <= row.keys()
            for row in result.json()["items"]
        )
    finally:
        event.remove(Engine, "before_cursor_execute", before)


def test_old_contact_default_hash_replays_but_changed_contact_still_conflicts(api, pg_settings):
    key = "legacy-default-record-key"
    row = create(api, key=key).json()
    engine = build_engine(pg_settings)
    from local_shop.records import NewReservation

    payload = NewReservation(
        customer_label="合成顾客甲", raw_text="电话需求原文，半斤分两袋"
    ).model_dump(mode="json")
    legacy = {
        k: v
        for k, v in payload.items()
        if k not in {"contact_name", "contact_phone", "delivery_address"}
    }
    with Session(engine) as session, session.begin():
        stored = session.scalar(select(IdempotencyKey).where(IdempotencyKey.key == key))
        stored.payload_hash = hashlib.sha256(
            json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    assert create(api, key=key).json() == row
    assert create(api, key=key, contact_phone="SYNTHETIC-CHANGED").status_code == 409
    engine.dispose()


def test_maintenance_inspection_never_deletes_candidates(pg_settings):
    import importlib.util
    from pathlib import Path

    module_path = Path(__file__).resolve().parents[3] / "scripts/maintenance_check.py"
    spec = importlib.util.spec_from_file_location("maintenance_check", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pg_settings.media_root.mkdir(parents=True, exist_ok=True)
    candidate = pg_settings.media_root / "12345678-1234-4234-8234-123456789abc.jpg"
    candidate.write_bytes(b"synthetic-not-real-image")
    result = module.inspect(pg_settings)
    assert (
        result["delete_supported"] is False
        and candidate.name in result["unreferenced_media_candidates"]
    )
    assert candidate.read_bytes() == b"synthetic-not-real-image"
