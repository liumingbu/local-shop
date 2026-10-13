"""Offline PostgreSQL + media bundle. Never drops/cleans databases or overwrites targets.
Only trusted, self-produced bundles may be restored: hashes detect damage, not authorship.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg import sql
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from .image_store import MAX_UPLOAD


class RecoveryConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: SecretStr
    pg_bin: Path


class RecoveryError(ValueError):
    """Sanitized operator-facing recovery error."""


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def connection_options(url):
    parsed = make_url(url)
    if (
        parsed.drivername != "postgresql+psycopg"
        or not parsed.host
        or not parsed.database
        or not parsed.username
    ):
        raise RecoveryError("Explicit PostgreSQL host, user and database required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", parsed.database):
        raise RecoveryError("Recovery requires a simple PostgreSQL database name")
    allowed = {"sslmode", "sslrootcert", "sslcert", "sslkey"}
    if set(parsed.query) - allowed:
        raise RecoveryError("Unsupported recovery connection options")
    return {
        "host": parsed.host,
        "port": parsed.port or 5432,
        "dbname": parsed.database,
        "user": parsed.username,
        "password": parsed.password or "",
        "connect_timeout": 3,
        **parsed.query,
    }


def pg_command(bin_dir, command, options, *args):
    binary = Path(bin_dir) / command
    if not binary.is_file():
        raise RecoveryError("Trusted PostgreSQL binaries required")
    # No URI/password in argv; ignore inherited PG service/host settings.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    mapping = {
        "host": "PGHOST",
        "port": "PGPORT",
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "connect_timeout": "PGCONNECT_TIMEOUT",
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
    }
    env.update({mapping[k]: str(v) for k, v in options.items() if v is not None})
    result = subprocess.run(
        [str(binary), *map(str, args)], env=env, capture_output=True, timeout=600
    )
    if result.returncode:
        # Error output can contain endpoint/user information; do not publish it.
        raise RecoveryError(
            f"{command} failed (exit {result.returncode}); destination stays offline"
        )
    return result.stdout.decode("utf-8").strip()


def inventory(options):
    with psycopg.connect(**options) as conn:
        identity = conn.execute(
            "SELECT current_database(),inet_server_addr()::text,inet_server_port()"
        ).fetchone()
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
        ]
        counts = {
            name: conn.execute(
                sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(name))
            ).fetchone()[0]
            for name in tables
        }
        if "alembic_version" not in tables or "media_objects" not in tables:
            raise RecoveryError("Not an initialized local-shop database")
        versions = sorted(row[0] for row in conn.execute("SELECT version_num FROM alembic_version"))
        media = {
            row[0]: {"size": row[1], "sha256": row[2]}
            for row in conn.execute("SELECT storage_key,size,sha256 FROM media_objects")
        }
        version = conn.execute("SHOW server_version_num").fetchone()[0]
    return {
        "source_fingerprint": hashlib.sha256(json.dumps(identity).encode()).hexdigest(),
        "table_counts": counts,
        "schema_versions": versions,
        "database_media": media,
        "server_version_num": version,
    }


def filename(name):
    if not isinstance(name, str) or not name.endswith(".jpg"):
        raise RecoveryError("Invalid media filename")
    if str(UUID(name[:-4])) + ".jpg" != name:
        raise RecoveryError("Noncanonical media filename")
    return name


def file_record(path):
    if path.is_symlink() or not path.is_file():
        raise RecoveryError("Symlinks and nonregular bundle files are forbidden")
    return {"size": path.stat().st_size, "sha256": digest(path)}


def copy_exclusive(source, target):
    # Caller supplies only generated/canonical names under new private directories.
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        outgoing.flush()
        os.fsync(outgoing.fileno())


def code_revision():
    root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
        )
        return {"sha": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"sha": None, "dirty": None}  # Operator must preserve release identity separately.


def backup(url, media_root, bundle, bin_dir, *, writers_stopped=False):
    if not writers_stopped:
        raise RecoveryError("Stop every writer before confirming offline backup")
    options = connection_options(url)
    media_root, bundle = Path(media_root), Path(bundle)
    if media_root.is_symlink() or not media_root.is_dir():
        raise RecoveryError("Existing non-symlink media directory required")
    # A new directory only. Never overwrite an earlier backup.
    bundle.mkdir(mode=0o700, parents=False, exist_ok=False)
    old_mask = os.umask(0o077)
    try:
        before = inventory(options)
        version = pg_command(bin_dir, "pg_dump", options, "--version")
        dump = bundle / "database.dump"
        pg_command(
            bin_dir,
            "pg_dump",
            options,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            dump,
        )
        (bundle / "media").mkdir(mode=0o700)
        files = {}
        for source in sorted(media_root.iterdir()):
            name = filename(source.name)
            record = file_record(source)
            if record["size"] > MAX_UPLOAD:
                raise RecoveryError("Media exceeds application limit")
            copy_exclusive(source, bundle / "media" / name)
            if file_record(bundle / "media" / name) != record:
                raise RecoveryError("Media changed during copy")
            files[name] = record
        for name, expected in before["database_media"].items():
            if files.get(filename(name)) != expected:
                raise RecoveryError("Database/media mismatch; backup is incomplete")
        if inventory(options) != before:
            raise RecoveryError("Database changed during offline backup")
        manifest = {
            "format": 1,
            "created_utc": datetime.now(UTC).isoformat(),
            "consistency": "operator-confirmed-all-writers-stopped",
            "pg_dump_version": version,
            "code_revision": code_revision(),
            **before,
            "dump": file_record(dump),
            "files": files,
        }
        with (bundle / "manifest.json").open("x", encoding="utf-8") as target:
            json.dump(manifest, target, ensure_ascii=False, indent=2)
            target.flush()
            os.fsync(target.fileno())
        verify(bundle)
        return manifest
    finally:
        os.umask(old_mask)


def verify(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise RecoveryError("Invalid bundle directory")
    if {p.name for p in bundle.iterdir()} != {"database.dump", "manifest.json", "media"}:
        raise RecoveryError("Incomplete or unexpected bundle entries")
    manifest_path, media = bundle / "manifest.json", bundle / "media"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 16 * 1024 * 1024:
        raise RecoveryError("Invalid manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not isinstance(manifest.get("files"), dict):
        raise RecoveryError("Unsupported bundle format")
    if media.is_symlink() or not media.is_dir():
        raise RecoveryError("Invalid media directory")
    if file_record(bundle / "database.dump") != manifest.get("dump"):
        raise RecoveryError("Database archive hash mismatch")
    if {p.name for p in media.iterdir()} != set(manifest["files"]):
        raise RecoveryError("Missing or unexpected media files")
    for name, expected in manifest["files"].items():
        if file_record(media / filename(name)) != expected or expected["size"] > MAX_UPLOAD:
            raise RecoveryError("Media hash mismatch")
    for name, expected in manifest.get("database_media", {}).items():
        if manifest["files"].get(filename(name)) != expected:
            raise RecoveryError("Database media inventory mismatch")
    return manifest


def restore(url, bundle, media_target, bin_dir, *, empty_target_confirmed=False):
    if not empty_target_confirmed:
        raise RecoveryError("A dedicated empty database and absent media target must be confirmed")
    manifest = verify(bundle)
    options = connection_options(url)
    media_target = Path(media_target)
    if media_target.exists() or media_target.is_symlink():
        raise RecoveryError("Media target must not already exist")
    with psycopg.connect(**options) as conn:
        identity = conn.execute(
            "SELECT current_database(),inet_server_addr()::text,inet_server_port()"
        ).fetchone()
        fingerprint = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        if fingerprint == manifest["source_fingerprint"]:
            raise RecoveryError("Refusing restore into original source database")
        objects = conn.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' "
            "AND c.relkind IN ('r','p','S','v','m','f')"
        ).fetchone()[0]
        objects += conn.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'"
        ).fetchone()[0]
        objects += conn.execute(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' "
            "AND t.typtype IN ('e','d','r','m')"
        ).fetchone()[0]
        objects += conn.execute(
            "SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' "
            "AND nspname NOT IN ('information_schema','public')"
        ).fetchone()[0]
        objects += conn.execute(
            "SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql'"
        ).fetchone()[0]
        if objects:
            raise RecoveryError("Restore database is not empty; no objects will be dropped")
        major = int(conn.execute("SHOW server_version_num").fetchone()[0]) // 10000
        if major != int(manifest["server_version_num"]) // 10000:
            raise RecoveryError("Cross-major restoration requires a separately tested migration")
    old_mask = os.umask(0o077)
    try:
        # mkdir is exclusive even if another process creates the target after validation.
        media_target.mkdir(mode=0o700, exist_ok=False)
        for name in manifest["files"]:
            copy_exclusive(Path(bundle) / "media" / name, media_target / name)
            if file_record(media_target / name) != manifest["files"][name]:
                raise RecoveryError("Copied media validation failed")
        # Recheck to detect changes while copying; use only trusted offline local bundles.
        verify(bundle)
        pg_command(
            bin_dir,
            "pg_restore",
            options,
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            options["dbname"],
            Path(bundle) / "database.dump",
        )
        current = inventory(options)
        for key in ("table_counts", "schema_versions", "database_media"):
            if current[key] != manifest[key]:
                raise RecoveryError("Restored inventory mismatch; keep target offline")
        return current
    finally:
        os.umask(old_mask)
        # DB + filesystem are not one atomic transaction. Keep services offline until
        # success. Partial new targets are retained on failure; nothing existing is erased.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--media-root", type=Path)
    parser.add_argument("--writers-stopped", action="store_true")
    parser.add_argument("--empty-target-confirmed", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "verify":
            result = verify(args.bundle)
        else:
            if args.media_root is None:
                raise RecoveryError("Explicit --media-root is required")
            settings = RecoveryConfig()
            url, bin_dir = settings.database_url.get_secret_value(), settings.pg_bin
            if args.action == "backup":
                result = backup(
                    url, args.media_root, args.bundle, bin_dir, writers_stopped=args.writers_stopped
                )
            else:
                result = restore(
                    url,
                    args.bundle,
                    args.media_root,
                    bin_dir,
                    empty_target_confirmed=args.empty_target_confirmed,
                )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "schema_versions": result["schema_versions"],
                    "table_counts": result["table_counts"],
                },
                ensure_ascii=False,
            )
        )
    except RecoveryError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit(
            "Recovery operation failed; keep services offline and inspect the "
            "trusted local bundle/target. No database was intentionally dropped. "
            "Connection details suppressed."
        ) from None


if __name__ == "__main__":
    main()
