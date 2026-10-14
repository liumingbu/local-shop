"""Read-only candidate inspection. There is intentionally no delete/apply option."""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from local_shop.config import Settings
from local_shop.db import build_engine
from local_shop.models import AuthSession, BrowserApproval, MediaObject
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


def inspect(settings):
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            # Explicit read-only transaction; listing never writes or deletes data/files.
            from sqlalchemy import text

            session.execute(text("SET TRANSACTION READ ONLY"))
            names = set(session.scalars(select(MediaObject.storage_key)))
            sessions = session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(
                    or_(AuthSession.revoked.is_(True), AuthSession.expires_at < datetime.now(UTC))
                )
            )
            approvals = session.scalar(
                select(func.count())
                .select_from(BrowserApproval)
                .where(
                    or_(
                        BrowserApproval.consumed.is_(True),
                        BrowserApproval.expires_at < datetime.now(UTC),
                    )
                )
            )
        candidates = [
            p.name
            for p in settings.media_root.rglob("*.jpg")
            if p.is_file()
            and not p.is_symlink()
            and re.fullmatch("[0-9a-f-]{36}\\.jpg", p.name)
            and p.name not in names
        ]
        return {
            "mode": "DRY_RUN_ONLY",
            "delete_supported": False,
            "expired_or_revoked_sessions": sessions,
            "expired_or_consumed_approvals": approvals,
            "unreferenced_media_candidates": sorted(candidates),
            "warning": (
                "Candidates are not approval to delete; "
                "verify retention, pending uploads and backups first."
            ),
        }
    finally:
        engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Read-only inspection accepts no apply/delete options")
    print(json.dumps(inspect(Settings()), ensure_ascii=False, indent=2))
