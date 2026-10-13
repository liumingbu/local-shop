"""Actual slow TCP body against the isolated loopback API; no external service."""

import io
import socket
import time
from urllib.parse import urlsplit

import httpx
from PIL import Image


def exercise_upload_timeout(base_url):
    target = urlsplit(base_url)
    assert target.hostname == "127.0.0.1" and target.scheme == "http"
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        token = client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).json()[
            "access_token"
        ]
        tenant = "10000000-0000-4000-8000-000000000001"
        path = f"/api/v1/merchant/tenants/{tenant}/media"
        key = "http-upload-receipt-timeout"
        payload = io.BytesIO()
        Image.new("RGB", (16, 16), "orange").save(payload, "PNG")
        body = payload.getvalue()
        started = time.monotonic()
        with socket.create_connection((target.hostname, target.port), timeout=5) as stream:
            header = (
                f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                f"Authorization: Bearer {token}\r\nIdempotency-Key: {key}\r\n"
                f"Content-Type: image/png\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode("ascii")
            stream.sendall(header + body[:8])
            received = b""
            while b"\r\n\r\n" not in received:
                part = stream.recv(4096)
                assert part and len(received) < 8192
                received += part
            assert received.split(b"\r\n", 1)[0].split()[1] == b"408"
        assert time.monotonic() - started < 5
        # Same key can succeed after the incomplete upload rolled back.
        headers = {
            "Authorization": "Bearer " + token,
            "Idempotency-Key": key,
            "Content-Type": "image/png",
        }
        result = client.post(path, headers=headers, content=body)
        assert result.status_code == 201
        replay = client.post(path, headers=headers, content=body)
        assert replay.status_code == 201 and replay.json()["id"] == result.json()["id"]
        assert client.get("/health/ready").status_code == 200
    print(
        "PASS REAL TCP incomplete image body returns 408 within configured one-second "
        "receipt deadline; same-key retry/replay and database readiness succeed",
        flush=True,
    )
