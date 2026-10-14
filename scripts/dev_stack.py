"""Foreground, loopback-only synthetic developer stack. Stop preserves its owned data."""

import argparse
import fcntl
import getpass
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from local_runtime import ROOT, port, ready

HOME = ROOT / "var/dev-stack"
MARKER = "local-shop-owned-synthetic-development-v1"


def state():
    try:
        return json.loads((HOME / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def write_state(value):
    temporary = HOME / "state.next.json"
    temporary.write_text(json.dumps(value))
    temporary.replace(HOME / "state.json")


def status():
    value = state()
    active = bool(
        value.get("instance")
        and not value.get("stopped")
        and time.time() - value.get("heartbeat", 0) < 10
    )
    result = {
        "kind": "owned synthetic development",
        "running": active,
        "data_preserved": (HOME / "pg/PG_VERSION").exists(),
        "health_source": "owning process heartbeat; cells may isolate PID/network namespaces",
    }
    if active:
        result |= {
            k: value[k] for k in ("api_url", "web_url", "started_at", "api_status", "web_status")
        }
    print(json.dumps(result, ensure_ascii=False))
    return result


def start(args):
    if HOME.is_symlink() or (ROOT / "var").is_symlink():
        raise SystemExit("Refusing symlink development directory")
    if HOME.exists() and not (HOME / "owner.json").exists():
        raise SystemExit("Unrecognized existing directory; no files modified")
    HOME.mkdir(parents=True, exist_ok=True)
    marker = HOME / "owner.json"
    if marker.exists() and json.loads(marker.read_text()).get("kind") != MARKER:
        raise SystemExit("Unrecognized data marker")
    if not marker.exists():
        marker.write_text(json.dumps({"kind": MARKER, "synthetic_only": True}))
    lock = (HOME / "lifecycle.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Developer stack already running")
    binary = Path(os.environ["PG_BIN"]).resolve()
    for name in ("postgres", "initdb", "pg_ctl"):
        if not (binary / name).is_file():
            raise SystemExit("Missing trusted PG_BIN tool: " + name)
    data = HOME / "pg"
    pg_port = port()
    api_port = args.api_port
    web_port = args.web_port
    if not (data / "PG_VERSION").exists():
        if data.exists() and any(data.iterdir()):
            raise SystemExit("Unknown nonempty PG directory; not initialized")
        subprocess.run(
            [
                str(binary / "initdb"),
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
    env = os.environ | {
        "APP_ENV": "development",
        "DEV_AUTH_ENABLED": "true",
        "WECHAT_LOGIN_ENABLED": "false",
        "WECHAT_APPID": "",
        "WECHAT_APP_SECRET": "",
        "API_HOST": "127.0.0.1",
        "API_PORT": str(api_port),
        "DATABASE_URL": f"postgresql+psycopg://{getpass.getuser()}@127.0.0.1:{pg_port}/postgres",
        "APP_SECRET_KEY": secrets.token_urlsafe(40),
        "MEDIA_ROOT": str(HOME / "media"),
        "PYTHONPATH": str(ROOT / "apps/api"),
        "VITE_ENABLE_DEVELOPMENT_LOGIN": "true",
        "LOCAL_SHOP_API_TARGET": f"http://127.0.0.1:{api_port}",
    }
    stopping = False
    processes = []
    pg_started = False

    def stop_signal(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    try:
        subprocess.run(
            [
                str(binary / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(HOME / "postgres.log"),
                "-o",
                f"-k '' -h 127.0.0.1 -p {pg_port}",
                "-w",
                "start",
            ],
            check=True,
        )
        pg_started = True
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "local_shop.seed"], cwd=ROOT, env=env, check=True)
        with (HOME / "services.log").open("a") as log:
            api = subprocess.Popen(
                [sys.executable, "-m", "local_shop"], cwd=ROOT, env=env, stdout=log, stderr=log
            )
            processes.append(api)
            ready(f"http://127.0.0.1:{api_port}/health/ready", api)
            web = subprocess.Popen(
                [
                    "node",
                    "node_modules/vite/bin/vite.js",
                    "apps/admin",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                    "--strictPort",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
            )
            processes.append(web)
            ready(f"http://127.0.0.1:{web_port}", web)
            value = {
                "instance": secrets.token_hex(16),
                "pid": os.getpid(),
                "start_ticks": Path(f"/proc/{os.getpid()}/stat")
                .read_text()
                .rsplit(")", 1)[1]
                .split()[19],
                "api_url": f"http://127.0.0.1:{api_port}",
                "web_url": f"http://127.0.0.1:{web_port}",
                "started_at": time.time(),
            }
            value |= {"heartbeat": time.time(), "api_status": 200, "web_status": 200}
            write_state(value)
            print(
                json.dumps(
                    {
                        "status": "READY",
                        "api_url": value["api_url"],
                        "web_url": value["web_url"],
                        "synthetic_only": True,
                    }
                ),
                flush=True,
            )
            deadline = time.monotonic() + args.duration
            with httpx.Client(trust_env=False, timeout=0.5) as probe:
                while not stopping and time.monotonic() < deadline:
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError(
                            "Child service exited; inspect protected local services.log"
                        )
                    try:
                        requested = json.loads((HOME / "stop.json").read_text())
                        if requested.get("instance") == value["instance"]:
                            break
                    except (OSError, ValueError):
                        pass
                    for name, url in [
                        ("api_status", value["api_url"] + "/health/ready"),
                        ("web_status", value["web_url"]),
                    ]:
                        try:
                            value[name] = probe.get(url).status_code
                        except httpx.HTTPError:
                            value[name] = "UNAVAILABLE"
                    value["heartbeat"] = time.time()
                    write_state(value)
                    time.sleep(0.5)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        if pg_started:
            subprocess.run(
                [str(binary / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"], check=True
            )
        write_state({"stopped": True, "data_preserved": True})
        lock.close()
        print("STOPPED; owned synthetic database and images preserved", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status", "diagnose"])
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=5173)
    parser.add_argument("--duration", type=int, default=3600)
    args = parser.parse_args()
    if not (
        1024 <= args.api_port <= 65535
        and 1024 <= args.web_port <= 65535
        and args.api_port != args.web_port
        and 1 <= args.duration <= 86400
    ):
        raise SystemExit("Invalid loopback ports/duration")
    if args.action == "start":
        start(args)
    elif args.action == "stop":
        value = state()
        if (
            not value.get("instance")
            or value.get("stopped")
            or time.time() - value.get("heartbeat", 0) > 10
        ):
            print("No current owned stack heartbeat; no process or data changed")
            return
        (HOME / "stop.json").write_text(json.dumps({"instance": value["instance"]}))
        for _ in range(100):
            current = state()
            if current.get("stopped"):
                print("Owned stack stopped and data preserved; owner acknowledged")
                return
            time.sleep(0.25)
        raise SystemExit("Stop requested but not acknowledged; no unrelated process was signalled")
    else:
        status()
        if args.action == "diagnose":
            print(
                json.dumps(
                    {
                        "python": sys.version.split()[0],
                        "venv_available": (ROOT / ".venv/bin/python").exists(),
                        "node_dependencies": (ROOT / "node_modules/vite").exists(),
                        "pg_bin_configured": bool(os.environ.get("PG_BIN")),
                        "public_access": False,
                        "persistent_hosting_guaranteed": False,
                    }
                )
            )
            subprocess.run(["node", "--version"], check=True)


if __name__ == "__main__":
    main()
