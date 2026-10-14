"""Same-computer synthetic runtime for bounded drills; never accepts an existing DB."""

import getpass
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def ready(url, process):
    with httpx.Client(trust_env=False, timeout=0.5) as client:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Isolated service exited; inspect local log")
            try:
                if client.get(url).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    raise RuntimeError("Isolated service startup timed out")


class Runtime:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="local-shop-synthetic-")
        self.folder = Path(self.tmp.name)
        self.bin = Path(os.environ["PG_BIN"]).resolve()
        self.data = self.folder / "pg"
        self.media = self.folder / "media"
        self.api = None
        self.pg_port = port()
        self.api_port = port()
        self.url = f"http://127.0.0.1:{self.api_port}"
        self.env = os.environ | {
            "APP_ENV": "test",
            "DEV_AUTH_ENABLED": "true",
            "WECHAT_LOGIN_ENABLED": "false",
            "WECHAT_APPID": "",
            "WECHAT_APP_SECRET": "",
            "API_HOST": "127.0.0.1",
            "API_PORT": str(self.api_port),
            "DATABASE_URL": f"postgresql+psycopg://{getpass.getuser()}@127.0.0.1:{self.pg_port}/postgres",
            "APP_SECRET_KEY": secrets.token_urlsafe(40),
            "MEDIA_ROOT": str(self.media),
            "PYTHONPATH": str(ROOT / "apps/api"),
        }
        subprocess.run(
            [
                str(self.bin / "initdb"),
                "-D",
                str(self.data),
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
                str(self.bin / "pg_ctl"),
                "-D",
                str(self.data),
                "-l",
                str(self.folder / "pg.log"),
                "-o",
                f"-k '' -h 127.0.0.1 -p {self.pg_port}",
                "-w",
                "start",
            ],
            check=True,
        )
        return self

    def migrate(self, source=ROOT, revision="head"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(source / "apps/api/alembic.ini"),
                "upgrade",
                revision,
            ],
            cwd=source,
            env=self.env | {"PYTHONPATH": str(source / "apps/api")},
            check=True,
        )

    def seed(self, source=ROOT):
        subprocess.run(
            [sys.executable, "-m", "local_shop.seed"],
            cwd=source,
            env=self.env | {"PYTHONPATH": str(source / "apps/api")},
            check=True,
        )

    def start(self, source=ROOT):
        self.stop()
        self.log = (self.folder / "api.log").open("a")
        self.api = subprocess.Popen(
            [sys.executable, "-m", "local_shop"],
            cwd=source,
            env=self.env | {"PYTHONPATH": str(source / "apps/api")},
            stdout=self.log,
            stderr=self.log,
        )
        ready(self.url + "/health/ready", self.api)
        return self.api

    def stop(self):
        if self.api:
            self.api.terminate()
            try:
                self.api.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.api.kill()
                self.api.wait(timeout=5)
            self.api = None
            self.log.close()

    def __exit__(self, *exc):
        self.stop()
        subprocess.run(
            [str(self.bin / "pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "stop"], check=True
        )
        self.tmp.cleanup()
