import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from local_shop.recovery import (
    RecoveryError,
    backup,
    connection_options,
    file_record,
    pg_command,
    restore,
    verify,
)

IMAGE = "20000000-0000-4000-8000-000000000001.jpg"


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "media").mkdir()
    (root / "database.dump").write_bytes(b"unit fixture, not a real PG dump")
    (root / "media" / IMAGE).write_bytes(b"unit media fixture")
    record = file_record(root / "media" / IMAGE)
    manifest = {
        "format": 1,
        "files": {IMAGE: record},
        "database_media": {IMAGE: record},
        "dump": file_record(root / "database.dump"),
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def test_bundle_integrity_only_does_not_claim_pg_restore(bundle):
    assert verify(bundle)["files"][IMAGE]["size"] > 0


@pytest.mark.parametrize("which", ["image", "dump", "missing", "extra"])
def test_bundle_damage_rejected(bundle, which):
    if which == "image":
        (bundle / "media" / IMAGE).write_bytes(b"damaged")
    elif which == "dump":
        (bundle / "database.dump").write_bytes(b"damaged")
    elif which == "missing":
        (bundle / "media" / IMAGE).unlink()
    else:
        (bundle / "media" / "extra.jpg").write_bytes(b"not in manifest")
    with pytest.raises(RecoveryError):
        verify(bundle)


def test_bundle_rejects_symlink_even_when_hash_matches(bundle, tmp_path):
    target = tmp_path / "original"
    target.write_bytes((bundle / "media" / IMAGE).read_bytes())
    (bundle / "media" / IMAGE).unlink()
    (bundle / "media" / IMAGE).symlink_to(target)
    with pytest.raises(RecoveryError, match="Symlinks"):
        verify(bundle)


def test_bundle_rejects_noncanonical_names_and_db_media_mismatch(bundle):
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["database_media"][IMAGE] = {"size": 1, "sha256": "0" * 64}
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RecoveryError, match="inventory"):
        verify(bundle)
    manifest["database_media"] = {}
    manifest["files"]["unsafe.jpg"] = manifest["files"].pop(IMAGE)
    (bundle / "media" / IMAGE).rename(bundle / "media" / "unsafe.jpg")
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify(bundle)


def test_recovery_requires_explicit_offline_empty_target_acknowledgement(tmp_path):
    with pytest.raises(RecoveryError, match="Stop every writer"):
        backup("unused", tmp_path / "source", tmp_path / "out", tmp_path)
    with pytest.raises(RecoveryError, match="dedicated empty database"):
        restore("unused", tmp_path / "source", tmp_path / "out", tmp_path)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///other",
        "postgresql+psycopg://user/db",
        "postgresql+psycopg://user@localhost/db?host=another",
        "postgresql+psycopg://user@localhost/dbname=other",
    ],
)
def test_connection_contract_rejects_implicit_or_conflicting_targets(url):
    with pytest.raises(RecoveryError):
        connection_options(url)


def test_pg_credentials_not_in_argv_and_inherited_service_ignored(tmp_path, monkeypatch):
    (tmp_path / "pg_dump").write_text("unit placeholder; never executed")
    seen = {}

    def run(args, **kwargs):
        seen.update(args=args, **kwargs)
        return SimpleNamespace(returncode=0, stdout=b"fixture", stderr=b"")

    monkeypatch.setenv("PGSERVICE", "unrelated-service")
    monkeypatch.setenv("PGHOST", "unrelated-host")
    monkeypatch.setattr("local_shop.recovery.subprocess.run", run)
    options = connection_options("postgresql+psycopg://synthetic:synthetic-only@127.0.0.1/db")
    assert pg_command(tmp_path, "pg_dump", options, "--version") == "fixture"
    assert "synthetic-only" not in repr(seen["args"])
    assert seen["env"]["PGPASSWORD"] == "synthetic-only"
    assert seen["env"]["PGHOST"] == "127.0.0.1"
    assert "PGSERVICE" not in seen["env"]
    assert seen["timeout"] == 600
    assert Path(seen["args"][0]).name == "pg_dump"
