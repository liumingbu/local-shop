"""Real HTTP image upload/association/download and durable-byte verification."""

import hashlib
import io

import httpx
from PIL import Image


def exercise_media(base_url):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        token = client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).json()[
            "access_token"
        ]
        headers = {"Authorization": "Bearer " + token}
        tenant = client.get("/api/v1/merchant/tenants", headers=headers).json()["items"][0]["id"]
        root = f"/api/v1/merchant/tenants/{tenant}"
        category = client.post(
            root + "/categories",
            headers=headers | {"Idempotency-Key": "http-media-category"},
            json={"name": "HTTP图片分类"},
        ).json()
        response = client.post(
            root + "/products",
            headers=headers | {"Idempotency-Key": "http-media-product"},
            json={
                "name": "HTTP图片商品",
                "unit": "份",
                "status": "PUBLISHED",
                "category_id": category["id"],
            },
        )
        assert response.status_code == 201
        product = response.json()
        ids = []
        for color in ("red", "blue"):
            output = io.BytesIO()
            Image.new("RGB", (24, 24), color).save(output, "PNG")
            response = client.post(
                root + "/media",
                headers=headers
                | {"Content-Type": "image/png", "Idempotency-Key": "http-media-" + color},
                content=output.getvalue(),
            )
            assert response.status_code == 201
            ids.append(response.json()["id"])
        response = client.put(
            root + "/products/" + product["id"] + "/images",
            headers=headers,
            json={"media_ids": ids[::-1], "expected_version": product["version"]},
        )
        assert response.status_code == 200
        public = client.get(f"/api/v1/stores/{tenant}/products/{product['id']}").json()
        assert [row["id"] for row in public["images"]] == ids[::-1]
        state = []
        for row in public["images"]:
            response = client.get(row["url"])
            assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
            assert Image.open(io.BytesIO(response.content)).format == "JPEG"
            state.append((row["url"], hashlib.sha256(response.content).hexdigest()))
        print(
            "PASS real HTTP: image upload/normalization/order/guarded download",
            flush=True,
        )
        return state


def verify_media_after_restart(base_url, state):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        for url, digest in state:
            response = client.get(url)
            assert (
                response.status_code == 200
                and hashlib.sha256(response.content).hexdigest() == digest
            )
    print(
        "PASS real HTTP after API + PostgreSQL restart: image associations and bytes durable",
        flush=True,
    )
