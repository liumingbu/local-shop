"""Actual start -> HTTP write -> stop -> restart -> HTTP read, owned synthetic stack only."""

import json
import os
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from dev_stack import HOME
from local_runtime import ROOT, port


def run():
    api_port, web_port = port(), port()
    env = os.environ.copy()
    command = [sys.executable, str(ROOT / "scripts/dev_stack.py")]

    def start():
        HOME.parent.mkdir(parents=True, exist_ok=True)
        log = (HOME.parent / "dev-stack-check.log").open("a")
        process = subprocess.Popen(
            command
            + [
                "start",
                "--api-port",
                str(api_port),
                "--web-port",
                str(web_port),
                "--duration",
                "90",
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Owned stack startup failed")
            try:
                value = json.loads((HOME / "state.json").read_text())
                if (
                    value.get("pid") == process.pid
                    and value.get("heartbeat")
                    and value.get("api_status") == 200
                ):
                    return process, log
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        raise RuntimeError("No ready heartbeat")

    def stop(process, log):
        subprocess.run(command + ["stop"], cwd=ROOT, env=env, check=True)
        assert process.wait(timeout=10) == 0
        log.close()

    process, log = start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{api_port}", trust_env=False, timeout=10
        ) as client:
            token = client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).json()[
                "access_token"
            ]
            root = "/api/v1/merchant/tenants/10000000-0000-4000-8000-000000000001/reservations"
            response = client.post(
                root,
                headers={"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid4())},
                json={"customer_label": "启动停止合成验证", "raw_text": "必须在重启后保留"},
            )
            assert response.status_code == 201
            row = response.json()
        subprocess.run(command + ["diagnose"], cwd=ROOT, env=env, check=True)
    finally:
        stop(process, log)
    process, log = start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{api_port}", trust_env=False, timeout=10
        ) as client:
            token = client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).json()[
                "access_token"
            ]
            response = client.get(
                root + "/" + row["id"], headers={"Authorization": "Bearer " + token}
            )
            assert response.status_code == 200 and response.json()["raw_text"] == row["raw_text"]
            with httpx.Client(trust_env=False, timeout=10) as web:
                assert (
                    web.get(f"http://127.0.0.1:{web_port}/health/ready").json()["status"] == "ready"
                )
        print(
            "PASS owned stack start/status/diagnose/stop/restart: "
            "real HTTP data and Vite proxy preserved; no browser claim"
        )
    finally:
        stop(process, log)


if __name__ == "__main__":
    run()
