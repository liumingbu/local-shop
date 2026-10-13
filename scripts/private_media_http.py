"""Real HTTP private image access before/after submission and across identities."""

import hashlib
import io

import httpx
from PIL import Image


def exercise_private_media(base_url):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        auth = {}
        for alias in ("merchant-a", "customer-a", "customer-b"):
            token = client.post("/api/v1/dev/session", json={"identity": alias}).json()[
                "access_token"
            ]
            auth[alias] = {"Authorization": "Bearer " + token}
        tenant = client.get("/api/v1/merchant/tenants", headers=auth["merchant-a"]).json()["items"][
            0
        ]["id"]
        root = f"/api/v1/merchant/tenants/{tenant}"
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "green").save(image, "PNG")
        response = client.post(
            f"/api/v1/stores/{tenant}/private-media?privacy_accepted=true",
            headers=auth["customer-a"]
            | {"Content-Type": "image/png", "Idempotency-Key": "http-private-image"},
            content=image.getvalue(),
        )
        assert response.status_code == 201
        mid = response.json()["id"]
        merchant_preview = root + f"/media/{mid}/content"
        assert client.get(merchant_preview, headers=auth["merchant-a"]).status_code == 404
        response = client.post(
            f"/api/v1/stores/{tenant}/inquiries",
            headers=auth["customer-a"] | {"Idempotency-Key": "http-private-inquiry"},
            json={"media_ids": [mid], "privacy_accepted": True},
        )
        assert response.status_code == 201
        inquiry = response.json()
        private_url = inquiry["attachments"][0]["url"]
        response = client.get(private_url, headers=auth["customer-a"])
        assert response.status_code == 200
        digest = hashlib.sha256(response.content).hexdigest()
        assert client.get(private_url, headers=auth["customer-b"]).status_code == 404
        assert client.get(private_url).status_code == 401
        assert client.get(merchant_preview, headers=auth["merchant-a"]).status_code == 200
        product = client.get(f"/api/v1/stores/{tenant}/products").json()["items"][0]
        assert (
            client.get(f"/api/v1/stores/{tenant}/products/{product['id']}/images/{mid}").status_code
            == 404
        )
        response = client.post(
            root + "/inquiries/" + inquiry["id"] + "/convert",
            headers=auth["merchant-a"] | {"Idempotency-Key": "http-private-convert"},
            json={
                "raw_text": "合成图片需求确认",
                "customer_label": "合成顾客",
                "expected_version": inquiry["version"],
            },
        )
        assert response.status_code == 201 and len(response.json()["attachments"]) == 1
        print(
            "PASS real HTTP: staged privacy/submit access/customer isolation/no public file route",
            flush=True,
        )
        return {
            "url": private_url,
            "owner": auth["customer-a"],
            "other": auth["customer-b"],
            "digest": digest,
        }


def verify_private_after_restart(base_url, state):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        response = client.get(state["url"], headers=state["owner"])
        assert (
            response.status_code == 200
            and hashlib.sha256(response.content).hexdigest() == state["digest"]
        )
        assert client.get(state["url"], headers=state["other"]).status_code == 404
    print(
        "PASS real HTTP after restart: private file bytes and identity checks durable", flush=True
    )
