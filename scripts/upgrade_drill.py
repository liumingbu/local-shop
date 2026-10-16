"""Run known old backend on synthetic data, then upgrade in place and verify every old value."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path

import httpx
import psycopg
from cancellation_http import exercise_cancellation
from catalog_http import exercise_catalog
from confirmation_http import exercise_confirmation
from customer_http import exercise_customer
from local_runtime import ROOT, Runtime
from media_http import exercise_media, verify_media_after_restart
from owner_http import exercise
from platform_http import exercise_platform, verify_platform_after_restart
from private_media_http import exercise_private_media, verify_private_after_restart
from psycopg import sql


def database_schema(runtime):
    with psycopg.connect(
        runtime.env["DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:", 1)
    ) as connection:
        columns = {}
        for table, name in connection.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name<>'alembic_version' "
            "ORDER BY table_name, ordinal_position"
        ):
            columns.setdefault(table, []).append(name)
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        return columns, revision


def snapshot(runtime, old_columns=None):
    with psycopg.connect(
        runtime.env["DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:", 1)
    ) as connection:
        tables = old_columns or database_schema(runtime)[0]
        result = {}
        for table in tables:
            values = []
            for (row,) in connection.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} t").format(sql.Identifier(table))
            ):
                if old_columns:
                    row = {key: value for key, value in row.items() if key in old_columns[table]}
                values.append(json.dumps(row, sort_keys=True, ensure_ascii=False))
            result[table] = sorted(values)
        return result


def files(runtime):
    return {
        p.relative_to(runtime.media).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in runtime.media.rglob("*.jpg")
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-ref", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not re.fullmatch("[0-9a-f]{40}", args.old_ref):
        raise SystemExit("Exact known old commit required")
    with Runtime() as runtime:
        old = runtime.folder / "old"
        old.mkdir()
        archive = runtime.folder / "old.tar"
        with archive.open("wb") as output:
            subprocess.run(
                ["git", "archive", args.old_ref, "apps/api"], cwd=ROOT, stdout=output, check=True
            )
        with tarfile.open(archive) as bundle:
            bundle.extractall(old, filter="data")
        runtime.migrate(old)
        runtime.seed(old)
        runtime.start(old)
        owner = exercise(runtime.url)
        exercise_catalog(runtime.url)
        images = exercise_media(runtime.url)
        exercise_customer(runtime.url)
        private = exercise_private_media(runtime.url)
        exercise_cancellation(runtime.url)
        exercise_confirmation(runtime.url)
        platform = exercise_platform(runtime.url)
        old_columns, old_revision = database_schema(runtime)
        before = snapshot(runtime, old_columns)
        media_before = files(runtime)
        runtime.stop()
        runtime.migrate()
        _, new_revision = database_schema(runtime)
        after = snapshot(runtime, old_columns)
        assert after == before, "Old row values changed during upgrade"
        assert files(runtime) == media_before, "Image bytes changed during upgrade"
        runtime.start()
        with httpx.Client(base_url=runtime.url, trust_env=False, timeout=10) as client:
            result = client.get(owner["url"], headers=owner["headers"])
            assert result.status_code == 200
            new = result.json()
            assert {key: new[key] for key in owner["detail"]} == owner["detail"]
            assert new["business_number"].startswith("LS")
            replay = client.post(
                owner["create_url"], headers=owner["create_headers"], json=owner["payload"]
            )
            assert replay.status_code == 201 and replay.json() == owner["original"]
            # Stored successful old command response stays byte-for-byte semantically old.
            outsider = client.post("/api/v1/dev/session", json={"identity": "merchant-b"}).json()[
                "access_token"
            ]
            assert (
                client.get(
                    owner["url"], headers={"Authorization": "Bearer " + outsider}
                ).status_code
                == 404
            )
            for name in media_before:
                mid = Path(name).stem
                url = (
                    "/api/v1/merchant/tenants/10000000-0000-4000-8000-000000000001"
                    f"/media/{mid}/content"
                )
                assert client.get(url).status_code == 401
            assert client.get("/api/v1/capabilities").json()["wechat_live_verified"] is False
        runtime.stop()
        runtime.start()
        verify_media_after_restart(runtime.url, images)
        verify_private_after_restart(runtime.url, private)
        verify_platform_after_restart(runtime.url, platform)
        with httpx.Client(base_url=runtime.url, trust_env=False, timeout=10) as client:
            assert (
                client.get(owner["url"], headers=owner["headers"]).json()["business_number"]
                == new["business_number"]
            )
        assert snapshot(runtime, old_columns) == before and files(runtime) == media_before
        report = {
            "old_sha": args.old_ref,
            "tested_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
            "old_tables_verified": len(before),
            "old_rows_verified": sum(map(len, before.values())),
            "images_verified": len(media_before),
            "upgrade": f"{old_revision} to {new_revision}",
            "checks": [
                "all old row values unchanged",
                "image bytes unchanged",
                "original details and history unchanged",
                "old idempotency response preserved",
                "new stable business number after restart",
                "cross-tenant and anonymous media access refused",
            ],
            "result": "PASS, synthetic same-computer only; NOT production upgrade",
        }
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
