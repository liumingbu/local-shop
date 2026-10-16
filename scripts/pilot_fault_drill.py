"""Bounded same-computer process/PG faults in new synthetic databases only.
No existing database, credentials, host or directory argument is accepted.
Fault hooks live only in a disposable child script, never in production API configuration.
"""

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import httpx
from local_runtime import ROOT, Runtime, ready

sys.path.insert(0, str(ROOT / "apps/api"))
from local_shop.communication_models import NotificationAttempt
from local_shop.config import Settings
from local_shop.db import build_engine
from local_shop.external_notifications import dispatch_once, prepare
from sqlalchemy.orm import Session

CHILD = r"""
import os,sys,time
from pathlib import Path
from uuid import UUID
from sqlalchemy import event
from sqlalchemy.orm import Session
from local_shop.config import Settings
from local_shop.db import build_engine
from local_shop.models import Reservation
from local_shop.main import create_app
from local_shop.external_notifications import dispatch_once,ProviderResult
import uvicorn
mode,barrier=sys.argv[1],Path(sys.argv[2])
def wait():
    barrier.write_text('synthetic reached')
    while True:time.sleep(.1)
if mode=='send':
    class Fake:
        def send(self,notice,deduplication_key):
            barrier.with_suffix('.calls').write_text('1')
            wait()
            return ProviderResult('ACCEPTED')
    dispatch_once(build_engine(Settings()),UUID(sys.argv[3]),Fake())
else:
    @event.listens_for(Session,'before_flush')
    def before(session,context,objects):
        if any(isinstance(x,Reservation) and x.raw_text=='H_PROCESS_'+mode for x in session.new):
            session.info['pilot_fault']=mode
            if mode=='before':wait()
    @event.listens_for(Session,'after_commit')
    def after(session):
        if session.info.get('pilot_fault')=='after':wait()
    uvicorn.run(create_app(),host='127.0.0.1',port=int(os.environ['API_PORT']),
                proxy_headers=False,access_log=False,log_level='warning')
"""
A = "10000000-0000-4000-8000-000000000001"
OWNER = UUID("00000000-0000-4000-8000-000000000001")


def wait_barrier(path, process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            raise RuntimeError("Synthetic child exited before barrier")
        time.sleep(0.05)
    raise RuntimeError("Synthetic fault barrier timeout")


def main():
    if len(sys.argv) != 1:
        raise SystemExit("No external target arguments accepted")
    with Runtime() as runtime:
        runtime.migrate()
        runtime.seed()
        runtime.start()
        script = runtime.folder / "fault_child.py"
        script.write_text(CHILD)
        with httpx.Client(base_url=runtime.url, trust_env=False, timeout=40) as client:

            def login(alias):
                r = client.post("/api/v1/dev/session", json={"identity": alias})
                assert r.status_code == 200
                return {"Authorization": "Bearer " + r.json()["access_token"]}

            owner, customer = login("merchant-a"), login("customer-a")
            root = f"/api/v1/merchant/tenants/{A}"
            r = client.put(
                root + "/store",
                headers=owner,
                json={
                    "name": "H合成故障店",
                    "expected_version": 0,
                    "published": True,
                    "allow_pickup": True,
                },
            )
            assert r.status_code == 200
            route = f"/api/v1/stores/{A}/reservations"

            def post(key, body):
                return client.post(route, headers=customer | {"Idempotency-Key": key}, json=body)

            def check(key, body):
                first = post(key, body)
                assert first.status_code == 201, first.text
                again = post(key, body)
                assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
                listing = client.get(
                    root + "/reservations", headers=owner, params={"q": body["raw_text"]}
                ).json()
                assert listing["total"] == 1
                feed = client.get(root + "/updates", headers=owner).json()
                matching = [x for x in feed["items"] if x["record_id"] == first.json()["id"]]
                assert len(matching) == 1
                return matching[0]["event_key"]

            for mode in ["before", "after"]:
                runtime.stop()
                barrier = runtime.folder / ("barrier-" + mode)
                runtime.log = (runtime.folder / "api.log").open("a")
                runtime.api = subprocess.Popen(
                    [sys.executable, str(script), mode, str(barrier)],
                    cwd=ROOT,
                    env=runtime.env,
                    stdout=runtime.log,
                    stderr=runtime.log,
                )
                ready(runtime.url + "/health/ready", runtime.api)
                body = {
                    "raw_text": "H_PROCESS_" + mode,
                    "customer_label": "合成故障顾客",
                    "privacy_accepted": True,
                }
                key = str(uuid4())
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(post, key, body)
                    wait_barrier(barrier, runtime.api)
                    runtime.api.kill()
                    runtime.api.wait(timeout=10)
                    try:
                        response = future.result(timeout=45)
                        assert response.status_code >= 500
                    except httpx.HTTPError:
                        pass
                runtime.start()
                event_key = check(key, body)
                print(
                    "PASS actual API process kill "
                    + mode
                    + " commit; same-key one record/one notice",
                    flush=True,
                )
            subprocess.run(
                [str(runtime.bin / "pg_ctl"), "-D", str(runtime.data), "-m", "fast", "-w", "stop"],
                check=True,
            )
            body = {
                "raw_text": "H_DATABASE_OUTAGE",
                "customer_label": "合成故障顾客",
                "privacy_accepted": True,
            }
            key = str(uuid4())
            try:
                unavailable = post(key, body)
                assert (
                    unavailable.status_code == 503
                    and unavailable.json()["code"] == "DATABASE_UNAVAILABLE"
                )
            finally:
                subprocess.run(
                    [
                        str(runtime.bin / "pg_ctl"),
                        "-D",
                        str(runtime.data),
                        "-l",
                        str(runtime.folder / "pg.log"),
                        "-o",
                        f"-k '' -h 127.0.0.1 -p {runtime.pg_port}",
                        "-w",
                        "start",
                    ],
                    check=True,
                )
            check(key, body)
            print(
                "PASS real PostgreSQL stopped/restarted; 503 then original retry one record/notice",
                flush=True,
            )
            settings = Settings(
                _env_file=None,
                app_env="test",
                database_url=runtime.env["DATABASE_URL"],
                app_secret_key=runtime.env["APP_SECRET_KEY"],
                dev_auth_enabled=True,
                media_root=runtime.media,
            )
            engine = build_engine(settings)
            with Session(engine) as session, session.begin():
                identifier = prepare(session, UUID(A), OWNER, "MERCHANT", event_key)
            barrier = runtime.folder / "send-barrier"
            with (runtime.folder / "sender.log").open("w") as log:
                sender = subprocess.Popen(
                    [sys.executable, str(script), "send", str(barrier), str(identifier)],
                    cwd=ROOT,
                    env=runtime.env,
                    stdout=log,
                    stderr=log,
                )
                try:
                    wait_barrier(barrier, sender)
                    sender.kill()
                    sender.wait(timeout=10)
                finally:
                    if sender.poll() is None:
                        sender.kill()
                        sender.wait(timeout=10)
            result = dispatch_once(engine, identifier, None)
            assert (
                result["status"] == "IN_PROGRESS"
                and result["outcome_unknown"]
                and not result["delivered"]
                and not result["read"]
            )
            assert barrier.with_suffix(".calls").read_text() == "1"
            with Session(engine) as session:
                assert session.get(NotificationAttempt, identifier).accepted_at is None
            engine.dispose()
            print(
                "PASS actual synthetic sender process interruption; unknown outcome retained; "
                "no resend or delivery/read claim",
                flush=True,
            )
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "scope": "isolated synthetic API/PG processes on dot computer",
                    "external_provider": "FAKE_ONLY",
                    "production_changed": False,
                    "file_write_failure": "separate test_pilot_closeout.py evidence",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
