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


def snapshot(runtime, old_tables=None):
    with psycopg.connect(
        runtime.env["DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:", 1)
    ) as connection:
        tables = old_tables or [
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename<>'alembic_version' ORDER BY tablename"
            )
        ]
        result = {}
        for table in tables:
            values = []
            for (row,) in connection.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} t").format(sql.Identifier(table))
            ):
                for field in (
                    {
                        "users": ["account_code"],
                        "reservations": [
                            "business_number",
                            "contact_name",
                            "contact_phone",
                            "delivery_address",
                            "confirmed_due_at",
                        ],
                    }.get(table, [])
                    if old_tables
                    else []
                ):
                    row.pop(field, None)
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
        before = snapshot(runtime)
        media_before = files(runtime)
        runtime.stop()
        runtime.migrate()
        after = snapshot(runtime, list(before))
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
        assert snapshot(runtime, list(before)) == before and files(runtime) == media_before
        report = {
            "old_sha": args.old_ref,
            "tested_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
            "old_tables_verified": len(before),
            "old_rows_verified": sum(map(len, before.values())),
            "images_verified": len(media_before),
            "upgrade": "0009_platform to 0011_verified_identity",
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
