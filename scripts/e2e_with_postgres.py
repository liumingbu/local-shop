"""Isolated PostgreSQL + real API + Vite + Chromium tests, all on this computer."""

import argparse
import getpass
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    "--serve-for",
    type=int,
    default=0,
    help="Keep isolated services alive for manual cloud-browser checks (seconds)",
)
parser.add_argument(
    "--http-only",
    action="store_true",
    help="Exercise real HTTP and restart persistence without a browser",
)
args = parser.parse_args()

root = Path(__file__).resolve().parents[1]
bin_dir = Path(os.environ["PG_BIN"]).resolve()


def wait_http(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Development process exited")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Development service startup timeout")


with tempfile.TemporaryDirectory(prefix="local-shop-e2e-") as directory:
    folder = Path(directory)
    data = folder / "data"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    subprocess.run(
        [str(bin_dir / "initdb"), "-D", str(data), "-A", "trust", "--no-locale", "--encoding=UTF8"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    processes = []
    subprocess.run(
        [
            str(bin_dir / "pg_ctl"),
            "-D",
            str(data),
            "-l",
            str(folder / "postgres.log"),
            "-o",
            f"-k '' -h 127.0.0.1 -p {port}",
            "-w",
            "start",
        ],
        check=True,
    )
    try:
        env = os.environ | {
            "APP_ENV": "test",
            "DATABASE_URL": f"postgresql+psycopg://{getpass.getuser()}@127.0.0.1:{port}/postgres",
            "APP_SECRET_KEY": secrets.token_urlsafe(32),
            "DEV_AUTH_ENABLED": "true",
            "API_HOST": "127.0.0.1",
            "API_PORT": "8000",
            "PYTHONPATH": str(root / "apps/api"),
            "MEDIA_ROOT": str(folder / "media"),
        }
        subprocess.run(
            [str(root / ".venv/bin/alembic"), "-c", "apps/api/alembic.ini", "upgrade", "head"],
            cwd=root,
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "local_shop.seed"], cwd=root, env=env, check=True)
        with (folder / "services.log").open("w") as log:
            api = subprocess.Popen(
                [sys.executable, "-m", "local_shop"], cwd=root, env=env, stdout=log, stderr=log
            )
            processes.append(api)
            web = subprocess.Popen(
                [
                    "node",
                    "node_modules/vite/bin/vite.js",
                    "apps/admin",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                    "--strictPort",
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
            )
            processes.append(web)
            wait_http("http://127.0.0.1:8000/health/ready", api)
            wait_http("http://127.0.0.1:5173", web)
            if args.http_only:
                from catalog_http import exercise_catalog
                from media_http import exercise_media, verify_media_after_restart
                from owner_http import exercise, verify_after_restart

                state = exercise("http://127.0.0.1:8000")
                exercise_catalog("http://127.0.0.1:8000")
                images = exercise_media("http://127.0.0.1:8000")
                api.terminate()
                api.wait(timeout=10)
                subprocess.run(
                    [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "restart"],
                    check=True,
                )
                api = subprocess.Popen(
                    [sys.executable, "-m", "local_shop"], cwd=root, env=env, stdout=log, stderr=log
                )
                processes.append(api)
                wait_http("http://127.0.0.1:8000/health/ready", api)
                verify_after_restart("http://127.0.0.1:8000", state)
                verify_media_after_restart("http://127.0.0.1:8000", images)
                result = subprocess.CompletedProcess([], 0)
            elif args.serve_for:
                print("ISOLATED_SERVICES_READY http://127.0.0.1:5173", flush=True)
                time.sleep(min(args.serve_for, 1800))
                result = subprocess.CompletedProcess([], 0)
            else:
                result = subprocess.run(
                    ["node", "node_modules/@playwright/test/cli.js", "test"], cwd=root, env=env
                )
            if result.returncode:
                print((folder / "services.log").read_text())
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        subprocess.run(
            [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"], check=True
        )
    raise SystemExit(result.returncode)
