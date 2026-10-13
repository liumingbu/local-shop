"""Real loopback HTTP live/ready-negative smoke; no business or WeChat simulation claim."""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
env = os.environ | {
    "PYTHONPATH": str(root / "apps/api"),
    "APP_ENV": "test",
    "API_HOST": "127.0.0.1",
    "API_PORT": str(port),
    "DATABASE_URL": "postgresql+psycopg://synthetic@127.0.0.1:1/unused",
    "APP_SECRET_KEY": secrets.token_urlsafe(32),
    "DEV_AUTH_ENABLED": "false",
}
with tempfile.TemporaryFile() as log:
    proc = subprocess.Popen(
        [sys.executable, "-m", "local_shop"], cwd=root, env=env, stdout=log, stderr=log
    )
    try:
        for attempt in range(50):
            if proc.poll() is not None:
                raise RuntimeError("API exited before becoming live")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health/live", timeout=0.5
                ) as res:
                    assert res.status == 200 and json.load(res) == {"status": "ok"}
                break
            except (OSError, TimeoutError):
                time.sleep(0.1)
        else:
            raise RuntimeError("API failed to become live within timeout")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=5)
            raise AssertionError("Readiness must not pass with unavailable database")
        except urllib.error.HTTPError as error:
            assert error.code == 503
            assert json.load(error)["code"] == "DATABASE_UNAVAILABLE"
        print("PASS: HTTP /health/live=200 and /health/ready=503 with unavailable database")
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
