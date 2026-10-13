"""HTTP catalog checks against the same isolated development application."""

import httpx


def exercise_catalog(base_url):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        token = client.post("/api/v1/dev/session", json={"identity": "merchant-a"}).json()[
            "access_token"
        ]
        headers = {"Authorization": "Bearer " + token}
        tenant = client.get("/api/v1/merchant/tenants", headers=headers).json()["items"][0]["id"]
        root = f"/api/v1/merchant/tenants/{tenant}"
        store = client.get(root + "/store", headers=headers).json()
        response = client.put(
            root + "/store",
            headers=headers,
            json={"name": store["name"], "expected_version": store["version"], "published": True},
        )
        assert response.status_code == 200
        assert client.get(f"/api/v1/stores/{tenant}").status_code == 200
        response = client.post(
            root + "/categories",
            headers=headers | {"Idempotency-Key": "http-category-01"},
            json={"name": "HTTP合成分类"},
        )
        assert response.status_code == 201
        category = response.json()
        payload = {
            "category_id": category["id"],
            "name": "HTTP合成商品",
            "unit": "斤",
            "reference_price": "12.50",
            "status": "PUBLISHED",
        }
        response = client.post(
            root + "/products",
            headers=headers | {"Idempotency-Key": "http-product-01"},
            json=payload,
        )
        assert response.status_code == 201
        product = response.json()
        public_url = f"/api/v1/stores/{tenant}/products/{product['id']}"
        response = client.get(public_url)
        assert response.status_code == 200 and response.json()["reference_price"] == "12.50"
        assert "stock" not in response.json() and "version" not in response.json()
        response = client.put(
            root + "/products/" + product["id"],
            headers=headers,
            json=payload | {"status": "ARCHIVED", "expected_version": product["version"]},
        )
        assert response.status_code == 200 and client.get(public_url).status_code == 404
        assert client.get(f"/api/v1/stores/{tenant}/products").json()["total"] == 0
        print(
            "PASS real HTTP: publish store/category/product/reference price/archive visibility",
            flush=True,
        )
