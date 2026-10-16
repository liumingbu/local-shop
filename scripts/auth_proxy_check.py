"""Real same-cloud Nginx/TLS -> API/PG source isolation, synthetic loopback clients only."""

import argparse
import json
import os
import ssl
import subprocess
import time
from pathlib import Path

import httpx
from linux_delivery_check import render
from local_runtime import ROOT, Runtime, port


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-shared", action="store_true")
    args = parser.parse_args()
    with Runtime() as rt:
        rt.migrate()
        rt.env.update(
            DEV_AUTH_ENABLED="false",
            WECHAT_LOGIN_ENABLED="true",
            WECHAT_APPID="wx0000000000000000",
            WECHAT_APP_SECRET="SYNTHETIC-PROXY-CHECK-ONLY",
            AUTH_TRUSTED_PROXY_IPS="127.0.0.1",
        )
        rt.start()
        folder = rt.folder
        cert, key = folder / "tls.crt", folder / "tls.key"
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
                "subjectAltName=IP:127.0.0.1",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
        )
        hp, tp = port(), port()
        candidate = folder / "candidate.conf"
        candidate.write_text(
            render(
                ROOT / "infra/nginx/local-shop.conf.template",
                {
                    "API_ADDRESS": f"127.0.0.1:{rt.api_port}",
                    "HTTP_BIND": f"127.0.0.1:{hp}",
                    "HTTPS_BIND": f"127.0.0.1:{tp}",
                    "SERVER_NAME": "localhost",
                    "PUBLIC_ORIGIN": f"https://localhost:{tp}",
                    "TLS_CERT": cert,
                    "TLS_KEY": key,
                    "ACCESS_LOG": folder / "access.log",
                },
            )
        )
        conf = folder / "nginx.conf"
        conf.write_text(
            f'daemon off; master_process off; pid "{folder}/nginx.pid"; '
            f'error_log "{folder}/error.log" warn; events {{ worker_connections 128; }} '
            f'http {{ client_body_temp_path "{folder}/body"; proxy_temp_path "{folder}/proxy"; '
            f'include "{candidate}"; }}'
        )
        nginx = Path(os.environ["NGINX_BIN"])
        with (folder / "nginx.log").open("w") as log:
            process = subprocess.Popen(
                [str(nginx), "-p", str(folder), "-c", str(conf)], stdout=log, stderr=log
            )
            try:
                context = ssl.create_default_context(cafile=str(cert))

                def client(ip):
                    return httpx.Client(
                        base_url=f"https://127.0.0.1:{tp}",
                        trust_env=False,
                        transport=httpx.HTTPTransport(verify=context, local_address=ip),
                        timeout=5,
                    )

                with client("127.0.0.2") as a, client("127.0.0.3") as b:
                    for _ in range(60):
                        try:
                            if a.get("/health/live").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Nginx failed to start")
                    # Avoid a minute boundary changing the rate bucket during this short sequence.
                    if time.time() % 60 > 54:
                        time.sleep(61 - time.time() % 60)
                    path = "/api/v1/auth/browser-approvals"
                    first = [a.post(path).status_code for _ in range(10)]
                    assert first == [201] * 10, first
                    a_limit = a.post(path).status_code
                    forged = a.post(
                        path,
                        headers={
                            "X-Forwarded-For": "192.0.2.8",
                            "X-Real-IP": "192.0.2.9",
                            "X-Local-Shop-Client-IP": "192.0.2.10",
                        },
                    ).status_code
                    second = b.post(path).status_code
                    assert a_limit == forged == 429
                    assert second == (429 if args.expect_shared else 201), second
                    assert (
                        a.post("/api/v1/dev/session", json={"identity": "merchant-a"}).status_code
                        == 404
                    )
                    if not args.expect_shared:
                        with httpx.Client(
                            base_url=rt.url,
                            trust_env=False,
                            transport=httpx.HTTPTransport(local_address="127.0.0.4"),
                        ) as direct:
                            for i in range(10):
                                assert (
                                    direct.post(
                                        path, headers={"X-Local-Shop-Client-IP": f"192.0.2.{i + 1}"}
                                    ).status_code
                                    == 201
                                )
                            assert (
                                direct.post(
                                    path, headers={"X-Local-Shop-Client-IP": "192.0.2.99"}
                                ).status_code
                                == 429
                            )
                        print("PASS untrusted direct transport ignores changing proxy header")
                    print(
                        json.dumps(
                            {
                                "first_client": first,
                                "exhausted": a_limit,
                                "forged_headers": forged,
                                "independent_second_client": second,
                                "result": "REPRODUCED_SHARED_BUCKET"
                                if args.expect_shared
                                else "PASS_INDEPENDENT_BUCKETS",
                                "scope": (
                                    "real Nginx TLS + API + PG; synthetic loopback clients; "
                                    "no external provider request"
                                ),
                            }
                        )
                    )
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    run()
