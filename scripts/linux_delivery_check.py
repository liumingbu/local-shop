"""Local component check: real Nginx/TLS/PG/API, not systemd activation or production.
Uses an ephemeral test certificate trusted only by this process, never the OS trust store.
"""

import argparse
import concurrent.futures
import getpass
import hashlib
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from backup_restore_drill import free_port, wait_ready
from catalog_http import exercise_catalog
from media_http import exercise_media
from owner_http import exercise
from private_media_http import exercise_private_media

ROOT = Path(__file__).resolve().parents[1]


def render(source, values):
    text = source.read_text()
    for key, value in values.items():
        if any(c in str(value) for c in ("\n", "\r", '"', "$", ";")):
            raise ValueError("Unsafe template value")
        text = text.replace("@@" + key + "@@", str(value))
    if "@@" in text:
        raise ValueError("Unresolved template token")
    return text


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-systemd",
        action="store_true",
        help="Explicitly exclude unavailable systemd verifier; never counts as verification",
    )
    args = parser.parse_args()
    systemd_blocked = False
    pg = Path(os.environ["PG_BIN"]).resolve()
    nginx = Path(os.environ["NGINX_BIN"]).resolve()
    assert nginx.is_file()
    subprocess.run([str(nginx), "-V"], check=True)
    with tempfile.TemporaryDirectory(prefix="local-shop-delivery-check-") as directory:
        folder = Path(directory)
        (folder / "logs").mkdir(mode=0o700)
        pg_port, api_port, http_port, tls_port = [free_port() for _ in range(4)]
        assert len({pg_port, api_port, http_port, tls_port}) == 4
        pg_data, media = folder / "pg", folder / "media"
        subprocess.run(
            [
                str(pg / "initdb"),
                "-D",
                str(pg_data),
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
                str(pg / "pg_ctl"),
                "-D",
                str(pg_data),
                "-l",
                str(folder / "pg.log"),
                "-o",
                f"-k '' -h 127.0.0.1 -p {pg_port}",
                "-w",
                "start",
            ],
            check=True,
        )
        processes = []
        try:
            env = os.environ | {
                "APP_ENV": "test",
                "DEV_AUTH_ENABLED": "true",
                "DATABASE_URL": f"postgresql+psycopg://{getpass.getuser()}@127.0.0.1:{pg_port}/postgres",
                "APP_SECRET_KEY": secrets.token_urlsafe(32),
                "API_HOST": "127.0.0.1",
                "API_PORT": str(api_port),
                "MEDIA_ROOT": str(media),
                "PYTHONPATH": str(ROOT / "apps/api"),
                "MEDIA_RECEIVE_TIMEOUT_SECONDS": "1",
            }
            subprocess.run(
                [str(ROOT / ".venv/bin/alembic"), "-c", "apps/api/alembic.ini", "upgrade", "head"],
                cwd=ROOT,
                env=env,
                check=True,
            )
            subprocess.run([sys.executable, "-m", "local_shop.seed"], cwd=ROOT, env=env, check=True)
            with (folder / "api.log").open("w") as log:
                api = subprocess.Popen(
                    [sys.executable, "-m", "local_shop"], cwd=ROOT, env=env, stdout=log, stderr=log
                )
                processes.append(api)
                base = f"http://127.0.0.1:{api_port}"
                wait_ready(base, api)
                owner = exercise(base)
                exercise_catalog(base)
                images = exercise_media(base)
                private = exercise_private_media(base)

                cert, key = folder / "test.crt", folder / "test.key"
                subprocess.run(
                    [
                        "openssl",
                        "req",
                        "-x509",
                        "-newkey",
                        "rsa:2048",
                        "-nodes",
                        "-days",
                        "1",
                        "-subj",
                        "/CN=localhost",
                        "-addext",
                        "subjectAltName=IP:127.0.0.1,DNS:localhost",
                        "-keyout",
                        str(key),
                        "-out",
                        str(cert),
                    ],
                    check=True,
                    capture_output=True,
                )
                access = folder / "access.log"
                values = {
                    "API_ADDRESS": f"127.0.0.1:{api_port}",
                    "HTTP_BIND": f"127.0.0.1:{http_port}",
                    "HTTPS_BIND": f"127.0.0.1:{tls_port}",
                    "SERVER_NAME": "localhost",
                    "PUBLIC_ORIGIN": f"https://localhost:{tls_port}",
                    "TLS_CERT": cert,
                    "TLS_KEY": key,
                    "ACCESS_LOG": access,
                }
                candidate = folder / "candidate.conf"
                candidate.write_text(render(ROOT / "infra/nginx/local-shop.conf.template", values))
                conf = folder / "nginx.conf"
                # Single-process component check. Production master/worker/systemd lifecycle
                # must be verified on the approved target server separately.
                conf.write_text(
                    f"daemon off; master_process off; worker_processes 1;\n"
                    f'pid "{folder}/nginx.pid"; error_log "{folder}/error.log" warn;\n'
                    "events { worker_connections 128; }\n"
                    f'http {{ client_body_temp_path "{folder}/body"; '
                    f'proxy_temp_path "{folder}/proxy"; '
                    f'include "{candidate}"; }}\n'
                )
                subprocess.run([str(nginx), "-p", str(folder), "-c", str(conf), "-t"], check=True)
                proxy = subprocess.Popen(
                    [str(nginx), "-p", str(folder), "-c", str(conf)], stdout=log, stderr=log
                )
                processes.append(proxy)
                context = ssl.create_default_context(cafile=str(cert))
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                secured = f"https://127.0.0.1:{tls_port}"
                with httpx.Client(
                    base_url=secured, verify=context, trust_env=False, timeout=5
                ) as client:
                    for _ in range(60):
                        try:
                            if client.get("/health/live").status_code == 200:
                                break
                        except httpx.TransportError:
                            time.sleep(0.1)
                    else:
                        raise AssertionError("TLS proxy not ready")
                    for version, label in [
                        (ssl.TLSVersion.TLSv1_2, "TLSv1.2"),
                        (ssl.TLSVersion.TLSv1_3, "TLSv1.3"),
                    ]:
                        exact = ssl.create_default_context(cafile=str(cert))
                        exact.minimum_version = exact.maximum_version = version
                        with socket.create_connection(("127.0.0.1", tls_port), timeout=5) as raw:
                            with exact.wrap_socket(raw, server_hostname="127.0.0.1") as tls:
                                assert tls.version() == label
                    with httpx.Client(trust_env=False, timeout=5) as plain:
                        redirect = plain.get(
                            f"http://127.0.0.1:{http_port}/health/live",
                            headers={"Host": "attacker.invalid"},
                        )
                        assert redirect.status_code == 308
                        assert (
                            redirect.headers["location"]
                            == f"https://localhost:{tls_port}/health/live"
                        )
                    for path in [
                        "/api/v1/dev/session",
                        "/api/v1/%64ev/session",
                        "/docs",
                        "/redoc",
                        "/openapi.json",
                        "/uploads/private.jpg",
                        "/media/private.jpg",
                        "/.env",
                        "/",
                    ]:
                        assert client.get(path).status_code == 404
                    assert client.post(
                        "/api/v1/dev/session", json={"alias": "merchant-a"}
                    ).status_code == 404
                    response = client.get("/health/ready")
                    assert response.status_code == 200
                    assert response.headers["x-content-type-options"] == "nosniff"
                    assert (
                        client.get(owner["url"], headers=owner["headers"]).json() == owner["detail"]
                    )
                    assert client.get(owner["url"]).status_code == 401
                    assert (
                        client.get(
                            owner["url"],
                            headers={"X-Forwarded-For": "127.0.0.1", "X-User-Id": "merchant-a"},
                        ).status_code
                        == 401
                    )
                    for image_url, image_hash in images:
                        response = client.get(image_url)
                        assert response.status_code == 200
                        assert hashlib.sha256(response.content).hexdigest() == image_hash
                    response = client.get(private["url"], headers=private["owner"])

                    assert (
                        response.status_code == 200
                        and hashlib.sha256(response.content).hexdigest() == private["digest"]
                    )
                    assert client.get(private["url"], headers=private["other"]).status_code == 404
                    response = client.post(
                        owner["create_url"], headers=owner["create_headers"], json=owner["payload"]
                    )
                    assert response.status_code == 201 and response.json() == owner["original"]
                    # An oversized synthetic body is rejected by the proxy.
                    response = client.post(
                        "/api/v1/stores/invalid/private-media", content=b"x" * (2 * 1024 * 1024 + 1)
                    )
                    assert response.status_code == 413
                    marker = "synthetic-private-query-marker"
                    client.get("/health/live?ignored=" + marker)
                    # Wait for the initial request burst to drain, then demonstrate real 429.
                    time.sleep(3)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                        responses = list(
                            pool.map(
                                lambda _: (
                                    client.get(
                                        "/api/v1/stores/00000000-0000-4000-8000-000000000001"
                                    )
                                ),
                                range(70),
                            )
                        )
                    limited = [response for response in responses if response.status_code == 429]
                    assert limited
                    for response in limited:
                        assert response.json()["code"] == "RATE_LIMITED"
                        assert response.headers["retry-after"] == "2"
                        assert response.headers["cache-control"] == "no-store"
                        assert response.headers["x-content-type-options"] == "nosniff"
                    time.sleep(0.1)
                    access_text = access.read_text()
                    assert marker not in access_text
                    assert "Bearer" not in access_text
                    for line in access_text.splitlines():
                        json.loads(line)
                print(
                    "PASS REAL Nginx/TLS1.2+TLS1.3: certificate verified by explicit ephemeral CA, "
                    "HTTPS fixed-host redirect, health/auth/image/idempotency proxy, "
                    "blocked dev/static paths, 2MiB limit, 429, query-free JSON access log",
                    flush=True,
                )
                # Verify the actual service candidate structurally, without activating systemd.
                unit = folder / "local-shop-api.service"
                unit.write_text(
                    render(
                        ROOT / "infra/systemd/local-shop-api.service.template",
                        {
                            "SERVICE_USER": getpass.getuser(),
                            "SERVICE_GROUP": getpass.getuser(),
                            "APP_ROOT": ROOT,
                            "ENV_FILE": folder / "service.env",
                            "MEDIA_ROOT": media,
                        },
                    )
                )
                if args.skip_systemd:
                    print(
                        "NOT_RUN systemd-analyze verification explicitly skipped; "
                        "earlier Dot run hit read-only /run/systemd",
                        flush=True,
                    )
                else:
                    check = subprocess.run(
                        ["systemd-analyze", "--man=no", "verify", str(unit)],
                        capture_output=True,
                        text=True,
                    )
                    if check.returncode:
                        systemd_blocked = True
                        print(
                            "BLOCKED systemd-analyze exit="
                            + str(check.returncode)
                            + ": "
                            + check.stderr.strip(),
                            flush=True,
                        )
                    else:
                        print(
                            "PASS systemd-analyze static verification (no service activation)",
                            flush=True,
                        )
                for patch, expected in [
                    ({}, "BLOCKED_ENVIRONMENT"),
                    (
                        {
                            "APP_ENV": "production",
                            "DEV_AUTH_ENABLED": "false",
                            "DATABASE_URL": "postgresql+psycopg://synthetic:placeholder@127.0.0.1/placeholder",
                        },
                        "BLOCKED_REAL_AUTH",
                    ),
                ]:
                    check = subprocess.run(
                        [sys.executable, "scripts/production_preflight.py"],
                        cwd=ROOT,
                        env=env | patch,
                        capture_output=True,
                        text=True,
                    )
                    assert check.returncode == 2 and expected in check.stdout
                    assert env["APP_SECRET_KEY"] not in check.stdout
                print(
                    "PASS fail-closed release guard; "
                    "systemd activation/production/real WeChat remain NOT_RUN/BLOCKED",
                    flush=True,
                )
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            subprocess.run(
                [str(pg / "pg_ctl"), "-D", str(pg_data), "-m", "fast", "-w", "stop"], check=True
            )
    return 2 if systemd_blocked else 0


if __name__ == "__main__":
    raise SystemExit(run())
