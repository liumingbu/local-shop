"""Create synthetic PG/media, stop the sole API writer, dump/copy, restore to a NEW DB.
Never accepts an existing DB URL, production host, or caller-supplied data directory.
Temporary dumps and private files are removed when the isolated drill ends.
"""

import getpass
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from cancellation_http import exercise_cancellation, verify_cancellation_after_restart  # noqa: E402
from catalog_http import exercise_catalog  # noqa: E402
from confirmation_http import exercise_confirmation, verify_confirmation_after_restart  # noqa: E402
from customer_http import exercise_customer, verify_customer_after_restart  # noqa: E402
from local_shop.recovery import (  # noqa: E402
    RecoveryError,
    backup,
    connection_options,
    inventory,
    restore,
    verify,
)
from media_http import exercise_media, verify_media_after_restart  # noqa: E402
from owner_http import exercise, verify_after_restart  # noqa: E402
from platform_http import exercise_platform, verify_platform_after_restart  # noqa: E402
from private_media_http import exercise_private_media, verify_private_after_restart  # noqa: E402


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Isolated API exited; local logs remain protected")
        try:
            with urllib.request.urlopen(url + "/health/ready", timeout=0.5) as reply:
                if reply.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Isolated API startup timed out")


def reject(call):
    try:
        call()
    except (RecoveryError, FileExistsError):
        return
    raise AssertionError("Unsafe recovery action was not rejected")


def run():
    bin_dir = Path(os.environ["PG_BIN"]).resolve()
    for command in ("postgres", "initdb", "pg_ctl", "pg_dump", "pg_restore"):
        assert (bin_dir / command).is_file(), "Trusted PG binaries are required"
    subprocess.run([str(bin_dir / "postgres"), "--version"], check=True)
    with tempfile.TemporaryDirectory(prefix="local-shop-restore-drill-") as directory:
        folder, pg_port, api_port = Path(directory), free_port(), free_port()
        data, media, bundle = folder / "data", folder / "source-media", folder / "bundle"
        media.mkdir(mode=0o700)
        subprocess.run(
            [
                str(bin_dir / "initdb"),
                "-D",
                str(data),
                "-A",
                "trust",
                "--no-locale",
                "--encoding=UTF8",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(bin_dir / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(folder / "postgres.log"),
                "-o",
                f"-k '' -h 127.0.0.1 -p {pg_port}",
                "-w",
                "start",
            ],
            check=True,
        )
        processes = []
        try:
            source_url = f"postgresql+psycopg://{getpass.getuser()}@127.0.0.1:{pg_port}/postgres"
            target_url = source_url.rsplit("/", 1)[0] + "/local_shop_restored"
            env = os.environ | {
                "APP_ENV": "test",
                "DEV_AUTH_ENABLED": "true",
                "DATABASE_URL": source_url,
                "APP_SECRET_KEY": secrets.token_urlsafe(32),
                "API_HOST": "127.0.0.1",
                "API_PORT": str(api_port),
                "MEDIA_ROOT": str(media),
                "PYTHONPATH": str(ROOT / "apps/api"),
            }
            subprocess.run(
                [str(ROOT / ".venv/bin/alembic"), "-c", "apps/api/alembic.ini", "upgrade", "head"],
                cwd=ROOT,
                env=env,
                check=True,
            )
            subprocess.run([sys.executable, "-m", "local_shop.seed"], cwd=ROOT, env=env, check=True)
            base_url = f"http://127.0.0.1:{api_port}"
            with (folder / "services.log").open("w") as log:
                api = subprocess.Popen(
                    [sys.executable, "-m", "local_shop"], cwd=ROOT, env=env, stdout=log, stderr=log
                )
                processes.append(api)
                wait_ready(base_url, api)
                owner = exercise(base_url)
                exercise_catalog(base_url)
                images = exercise_media(base_url)
                customer = exercise_customer(base_url)
                private = exercise_private_media(base_url)
                cancellation = exercise_cancellation(base_url)
                confirmation = exercise_confirmation(base_url)
                platform = exercise_platform(base_url)
                api.terminate()
                api.wait(timeout=10)
                assert api.poll() is not None  # Sole writer actually stopped, not just a flag.
                before = inventory(connection_options(source_url))
                reject(lambda: backup(source_url, media, bundle, bin_dir))
                cli = [sys.executable, "-m", "local_shop.recovery"]
                cli_env = env | {"PG_BIN": str(bin_dir)}
                subprocess.run(
                    cli
                    + [
                        "backup",
                        "--bundle",
                        str(bundle),
                        "--media-root",
                        str(media),
                        "--writers-stopped",
                    ],
                    cwd=ROOT,
                    env=cli_env,
                    check=True,
                    capture_output=True,
                )
                checked = subprocess.run(
                    cli + ["verify", "--bundle", str(bundle)],
                    cwd=ROOT,
                    env=cli_env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                assert json.loads(checked.stdout)["status"] == "ok"
                manifest = verify(bundle)
                assert manifest["table_counts"] == before["table_counts"]
                assert len(manifest["files"]) >= 2
                assert manifest["schema_versions"] == ["0009_platform"]
                assert bundle.stat().st_mode & 0o077 == 0
                for path in [
                    bundle / "database.dump",
                    bundle / "manifest.json",
                    *(bundle / "media").iterdir(),
                ]:
                    assert path.stat().st_mode & 0o077 == 0
                reject(lambda: backup(source_url, media, bundle, bin_dir, writers_stopped=True))
                reject(
                    lambda: restore(
                        source_url,
                        bundle,
                        folder / "forbidden-source",
                        bin_dir,
                        empty_target_confirmed=True,
                    )
                )
                assert inventory(connection_options(source_url)) == before
                print(
                    "PASS offline bundle: real pg_dump + media hashes/schema/counts; "
                    "private permissions; no overwrite/source restore",
                    flush=True,
                )

                # Damage is rejected before opening/restoring the destination database.
                corrupt = folder / "corrupt"
                shutil.copytree(bundle, corrupt)
                image = next((corrupt / "media").iterdir())
                image.write_bytes(b"intentional synthetic corruption")
                reject(lambda: verify(corrupt))
                reject(
                    lambda: restore(
                        target_url,
                        corrupt,
                        folder / "bad-restore",
                        bin_dir,
                        empty_target_confirmed=True,
                    )
                )
                assert not (folder / "bad-restore").exists()
                corrupt_dump = folder / "corrupt-dump"
                shutil.copytree(bundle, corrupt_dump)
                with (corrupt_dump / "database.dump").open("ab") as target:
                    target.write(b"intentional corruption")
                reject(lambda: verify(corrupt_dump))
                print(
                    "PASS damaged image/database archives rejected before target restore",
                    flush=True,
                )

                incomplete_media = folder / "incomplete-source-media"
                shutil.copytree(media, incomplete_media)
                next(incomplete_media.iterdir()).unlink()  # Only synthetic copied fixtures.
                reject(
                    lambda: backup(
                        source_url,
                        incomplete_media,
                        folder / "incomplete-bundle",
                        bin_dir,
                        writers_stopped=True,
                    )
                )
                reject(lambda: verify(folder / "incomplete-bundle"))
                assert inventory(connection_options(source_url)) == before
                with psycopg.connect(**connection_options(source_url), autocommit=True) as conn:
                    conn.execute("CREATE DATABASE local_shop_restored")
                    conn.execute("CREATE DATABASE local_shop_occupied")
                occupied_url = source_url.rsplit("/", 1)[0] + "/local_shop_occupied"
                with psycopg.connect(**connection_options(occupied_url)) as conn:
                    conn.execute(
                        "CREATE FUNCTION public.existing_marker() RETURNS int "
                        "LANGUAGE SQL AS 'SELECT 42'"
                    )
                reject(
                    lambda: restore(
                        occupied_url,
                        bundle,
                        folder / "occupied-media",
                        bin_dir,
                        empty_target_confirmed=True,
                    )
                )
                with psycopg.connect(**connection_options(occupied_url)) as conn:
                    assert conn.execute("SELECT existing_marker()").fetchone() == (42,)
                assert not (folder / "occupied-media").exists()
                print(
                    "PASS missing referenced image prevents complete backup; "
                    "existing function-only database preserved",
                    flush=True,
                )
                target_media = folder / "restored-media"
                reject(lambda: restore(target_url, bundle, target_media, bin_dir))
                subprocess.run(
                    cli
                    + [
                        "restore",
                        "--bundle",
                        str(bundle),
                        "--media-root",
                        str(target_media),
                        "--empty-target-confirmed",
                    ],
                    cwd=ROOT,
                    env=cli_env | {"DATABASE_URL": target_url},
                    check=True,
                    capture_output=True,
                )
                restored = inventory(connection_options(target_url))
                print(
                    "RESTORE_METRICS "
                    + json.dumps(
                        {
                            "tables": len(restored["table_counts"]),
                            "rows": sum(restored["table_counts"].values()),
                            "media_files": len(manifest["files"]),
                            "archive_bytes": manifest["dump"]["size"],
                            "code_revision": manifest["code_revision"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                for key in ("table_counts", "schema_versions", "database_media"):
                    assert restored[key] == before[key]
                reject(
                    lambda: restore(
                        target_url, bundle, target_media, bin_dir, empty_target_confirmed=True
                    )
                )
                reject(
                    lambda: restore(
                        target_url,
                        bundle,
                        folder / "must-not-replace-db",
                        bin_dir,
                        empty_target_confirmed=True,
                    )
                )
                assert inventory(connection_options(target_url)) == restored
                print(
                    "PASS real pg_restore into separate empty DB: all table counts/schema/media "
                    "inventory match; occupied targets refused",
                    flush=True,
                )
                subprocess.run(
                    [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "restart"],
                    check=True,
                )
                env |= {"DATABASE_URL": target_url, "MEDIA_ROOT": str(target_media)}
                api = subprocess.Popen(
                    [sys.executable, "-m", "local_shop"], cwd=ROOT, env=env, stdout=log, stderr=log
                )
                processes.append(api)
                wait_ready(base_url, api)
                verify_after_restart(base_url, owner)
                verify_media_after_restart(base_url, images)
                verify_customer_after_restart(base_url, customer)
                verify_private_after_restart(base_url, private)
                verify_cancellation_after_restart(base_url, cancellation)
                verify_confirmation_after_restart(base_url, confirmation)
                verify_platform_after_restart(base_url, platform)
                print(
                    "PASS RESTORED-DB HTTP: original records/revisions/cancellation/platform audit/"
                    "idempotency/public and private image bytes/identity isolation",
                    flush=True,
                )
                print(
                    "Synthetic offline drill only; no production backups or deployment. "
                    "Temporary bundle is not uploaded.",
                    flush=True,
                )
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            subprocess.run(
                [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"], check=True
            )


if __name__ == "__main__":
    run()
