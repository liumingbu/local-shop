"""Start an isolated local PG instance for tests and stop it before this process exits.
PG_BIN must point to existing trusted PostgreSQL binaries. Never targets an existing data dir.
"""

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
bin_dir = Path(os.environ["PG_BIN"]).resolve()
for name in ("postgres", "initdb", "pg_ctl"):
    if not (bin_dir / name).is_file():
        raise SystemExit(f"Missing PostgreSQL binary: {name}")
with tempfile.TemporaryDirectory(prefix="local-shop-pg-") as directory:
    data = Path(directory) / "data"
    log = Path(directory) / "postgres.log"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    subprocess.run([str(bin_dir / "postgres"), "--version"], check=True)
    subprocess.run(
        [str(bin_dir / "initdb"), "-D", str(data), "-A", "trust", "--no-locale", "--encoding=UTF8"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    started = False
    try:
        subprocess.run(
            [
                str(bin_dir / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(log),
                "-o",
                f"-k '' -h 127.0.0.1 -p {port}",
                "-w",
                "start",
            ],
            check=True,
        )
        started = True
        import getpass

        env = os.environ | {
            "TEST_DATABASE_ADMIN_URL": f"postgresql://{getpass.getuser()}@127.0.0.1:{port}/postgres"
        }
        import psycopg

        with psycopg.connect(env["TEST_DATABASE_ADMIN_URL"]) as conn:
            conn.execute("CREATE TABLE persistence_probe (value integer NOT NULL)")
            conn.execute("INSERT INTO persistence_probe VALUES (42)")
        subprocess.run(
            [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "restart"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with psycopg.connect(env["TEST_DATABASE_ADMIN_URL"]) as conn:
            assert conn.execute("SELECT value FROM persistence_probe").fetchone() == (42,)
        print("PASS: PostgreSQL restart persistence", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *sys.argv[1:]], cwd=root, env=env
        )
    finally:
        if started:
            subprocess.run(
                [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"], check=True
            )
    raise SystemExit(result.returncode)
