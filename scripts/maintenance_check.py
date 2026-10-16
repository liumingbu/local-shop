"""Read-only candidate inspection. There is intentionally no delete/apply option."""

import argparse
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from local_shop.communication_models import NotificationAttempt
from local_shop.config import Settings
from local_shop.db import build_engine
from local_shop.models import AuthSession, BrowserApproval, MediaObject
from local_shop.recovery import verify
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


def inspect(settings, backup_bundle=None):
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
            minute = int(datetime.now(UTC).timestamp()) // 60
            rate = session.execute(
                text(
                    "SELECT count(*), count(*) FILTER (WHERE "
                    "CASE WHEN bucket ~ ':[0-9]{1,12}$' THEN "
                    "substring(bucket from ':([0-9]{1,12})$')::bigint < :minute "
                    "ELSE false END) FROM auth_rate_windows"
                ),
                {"minute": minute},
            ).one()
            database_bytes = session.scalar(text("SELECT pg_database_size(current_database())"))
            largest = session.execute(
                text(
                    "SELECT relname, pg_total_relation_size(relid) "
                    "FROM pg_catalog.pg_statio_user_tables ORDER BY "
                    "pg_total_relation_size(relid) DESC LIMIT 10"
                )
            ).all()
            uncertain = session.scalar(
                select(func.count())
                .select_from(NotificationAttempt)
                .where(NotificationAttempt.status.in_(["IN_PROGRESS", "TIMEOUT", "UNKNOWN"]))
            )
        disk_root = settings.media_root
        while not disk_root.exists():
            disk_root = disk_root.parent
        disk = shutil.disk_usage(disk_root)
        observed_files = []
        truncated = False
        for path in settings.media_root.rglob("*.jpg"):
            if len(observed_files) >= 10000:
                truncated = True
                break
            if path.is_file() and not path.is_symlink():
                observed_files.append(path)
        backup = {"status": "NOT_CONFIGURED", "restore_tested_by_this_check": False}
        if backup_bundle is not None:
            try:
                checked = verify(backup_bundle)
                backup = {
                    "status": "HASH_VERIFIED",
                    "created_utc": checked.get("created_utc"),
                    "schema_versions": checked.get("schema_versions"),
                    "restore_tested_by_this_check": False,
                }
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                backup = {"status": "INVALID_OR_UNAVAILABLE", "restore_tested_by_this_check": False}
        candidates = [
            p.name
            for p in observed_files
            if p.is_file()
            and not p.is_symlink()
            and re.fullmatch("[0-9a-f-]{36}\\.jpg", p.name)
            and p.name not in names
        ]
        return {
            "mode": "DRY_RUN_ONLY",
            "observed_utc": datetime.now(UTC).isoformat(),
            "rate_window_rows": rate[0],
            "expired_rate_window_candidates": rate[1],
            "notification_unknown_or_in_progress": uncertain,
            "notification_retry_performed": False,
            "database_bytes": database_bytes,
            "largest_tables_bytes": [{"table": name, "bytes": size} for name, size in largest],
            "observed_media_files": len(observed_files),
            "observed_media_bytes": sum(p.stat().st_size for p in observed_files),
            "media_scan_truncated": truncated,
            "filesystem_free_bytes": disk.free,
            "backup": backup,
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backup-bundle",
        type=Path,
        help="Optional existing backup to verify read-only; never creates/restores it",
    )
    args = parser.parse_args()
    print(json.dumps(inspect(Settings(), args.backup_bundle), ensure_ascii=False, indent=2))
