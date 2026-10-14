"""Bounded same-Dot benchmark: synthetic PG, 2 tenants x 30 products x 200 records, 10 workers."""

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from local_runtime import ROOT, Runtime

sys.path.insert(0, str(ROOT / "apps/api"))
from local_shop.config import Settings
from local_shop.db import build_engine
from local_shop.formal_auth import issue
from local_shop.models import TenantMember, User, WeChatIdentity
from sqlalchemy.orm import Session


def setup(runtime):
    runtime.migrate()
    runtime.seed()
    runtime.env |= {
        "DEV_AUTH_ENABLED": "false",
        "WECHAT_LOGIN_ENABLED": "true",
        "WECHAT_APPID": "wx0000000000000000",
        "WECHAT_APP_SECRET": "SYNTHETIC-BENCHMARK-ONLY",
    }
    settings = Settings(
        _env_file=None,
        **{
            k.lower(): v
            for k, v in runtime.env.items()
            if k
            in {
                "APP_ENV",
                "DEV_AUTH_ENABLED",
                "WECHAT_LOGIN_ENABLED",
                "WECHAT_APPID",
                "WECHAT_APP_SECRET",
                "DATABASE_URL",
                "APP_SECRET_KEY",
                "MEDIA_ROOT",
            }
        },
    )
    engine = build_engine(settings)
    owners = []
    with Session(engine) as session, session.begin():
        for n in (1, 2):
            tenant = f"10000000-0000-4000-8000-{n:012d}"
            uid = uuid4()
            session.add(
                User(
                    id=uid,
                    identity_type="WECHAT",
                    display_name="Synthetic benchmark",
                    status="ACTIVE",
                )
            )
            session.flush()
            session.add(
                WeChatIdentity(
                    appid=settings.wechat_appid, openid=f"synthetic-benchmark-{n}", user_id=uid
                )
            )
            session.add(
                TenantMember(tenant_id=UUID(tenant), user_id=uid, role="OWNER", status="ACTIVE")
            )
            owners.append((tenant, issue(session, settings, uid)["access_token"]))
    engine.dispose()
    runtime.start()
    records = []
    with httpx.Client(base_url=runtime.url, trust_env=False, timeout=10) as client:
        for tenant, token in owners:
            root = "/api/v1/merchant/tenants/" + tenant
            headers = {"Authorization": "Bearer " + token}

            def post(path, data):
                r = client.post(
                    root + path, json=data, headers=headers | {"Idempotency-Key": str(uuid4())}
                )
                assert r.status_code == 201, r.status_code
                return r.json()

            r = client.put(
                root + "/store",
                json={
                    "name": "合成基准店",
                    "expected_version": 0,
                    "published": True,
                    "allow_pickup": True,
                },
                headers=headers,
            )
            assert r.status_code == 200
            category = post("/categories", {"name": "合成分类"})
            products = [
                post(
                    "/products",
                    {
                        "category_id": category["id"],
                        "name": f"合成商品{i:02}",
                        "unit": "斤",
                        "spec": "散装",
                        "reference_price": "12.50",
                        "status": "PUBLISHED",
                        "supply_status": "REGULAR",
                    },
                )
                for i in range(30)
            ]
            ids = []
            for i in range(200):
                record = post(
                    "/reservations",
                    {
                        "customer_label": f"合成顾客{i:03}",
                        "raw_text": f"基准需求{i:03} 半斤分两袋",
                        "mark_confirmed": i % 2 == 0,
                        "items": [
                            {
                                "name": products[i % 30]["name"],
                                "quantity": "0.5",
                                "unit": "斤",
                                "spec": "散装",
                                "product_id": products[i % 30]["id"],
                            }
                        ],
                    },
                )
                ids.append(record["id"])
            records.append(ids)
    runtime.stop()
    return owners, records


def measure(runtime, owners, records, source=ROOT):
    process = runtime.start(source)
    rss = []
    stop = threading.Event()

    def memory():
        while not stop.wait(0.02):
            try:
                lines = Path(f"/proc/{process.pid}/status").read_text().splitlines()
                rss.append(int(next(x for x in lines if x.startswith("VmRSS:")).split()[1]))
            except (OSError, StopIteration):
                pass

    def cpu():
        fields = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")

    def request_one(client, i):
        tenant, token = owners[i % 2]
        root = "/api/v1/merchant/tenants/" + tenant
        paths = [
            root + "/workbench-summary",
            root + "/reservations?limit=20&page=5",
            root + "/reservations?q=" + httpx.QueryParams({"q": "基准需求"}).get("q"),
            root + "/reservations/" + records[i % 2][i % 200],
            f"/api/v1/stores/{tenant}/products?limit=20",
        ]
        begin = time.perf_counter()
        response = client.get(paths[(i // 2) % 5], headers={"Authorization": "Bearer " + token})
        elapsed = (time.perf_counter() - begin) * 1000
        if response.status_code != 200:
            return elapsed, response.status_code
        value = response.json()
        if "items" in value and any(x.get("tenant_id", tenant) != tenant for x in value["items"]):
            raise RuntimeError("Tenant scope mismatch")
        return elapsed, 200

    def worker(n, count):
        with httpx.Client(base_url=runtime.url, trust_env=False, timeout=10) as client:
            return [request_one(client, n + 10 * i) for i in range(count)]

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda n: worker(n, 2), range(10)))
    sampler = threading.Thread(target=memory, daemon=True)
    sampler.start()
    before = cpu()
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        rows = [item for batch in pool.map(lambda n: worker(n, 50), range(10)) for item in batch]
    wall = time.perf_counter() - start
    used = cpu() - before
    stop.set()
    sampler.join()
    values = sorted(x[0] for x in rows)
    result = {
        "requests": len(rows),
        "concurrency": 10,
        "errors": sum(x[1] != 200 for x in rows),
        "latency_ms": {
            "p50": round(statistics.median(values), 2),
            "p95": round(values[int(len(values) * 0.95) - 1], 2),
            "max": round(max(values), 2),
        },
        "wall_seconds": round(wall, 3),
        "api_cpu_seconds": round(used, 3),
        "api_peak_rss_kib": max(rss, default=0),
    }
    runtime.stop()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    import re
    import tarfile

    if not re.fullmatch("[0-9a-f]{40}", args.baseline_ref):
        raise SystemExit("Exact known baseline SHA required")
    with Runtime() as runtime:
        archive = runtime.folder / "baseline.tar"
        baseline = runtime.folder / "baseline"
        baseline.mkdir()
        with archive.open("wb") as output:
            subprocess.run(
                ["git", "archive", args.baseline_ref, "apps/api"],
                cwd=ROOT,
                stdout=output,
                check=True,
            )
        with tarfile.open(archive) as bundle:
            bundle.extractall(baseline, filter="data")
        owners, records = setup(runtime)
        before = measure(runtime, owners, records, baseline)
        after = measure(runtime, owners, records)
        report = {
            "kind": "same-Dot synthetic reference, NOT production capacity",
            "baseline_sha": args.baseline_ref,
            "tested_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
            "dataset": {"tenants": 2, "products_per_tenant": 30, "records_per_tenant": 200},
            "identity": (
                "Real opaque sessions and DB permissions; synthetic provider identities; "
                "no WeChat network"
            ),
            "environment": {
                "python": sys.version.split()[0],
                "cpu_visible": os.cpu_count(),
                "postgres": subprocess.check_output(
                    [str(runtime.bin / "postgres"), "--version"], text=True
                ).strip(),
            },
            "before": before,
            "after": after,
        }
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if before["errors"] or after["errors"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
