"""Real HTTP owner workflow assertions (synthetic records only)."""

import httpx


def exercise(base_url):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        tokens = {}
        tenants = {}
        for alias in ("merchant-a", "merchant-b"):
            response = client.post("/api/v1/dev/session", json={"identity": alias})
            assert response.status_code == 200
            tokens[alias] = {"Authorization": "Bearer " + response.json()["access_token"]}
            response = client.get("/api/v1/merchant/tenants", headers=tokens[alias])
            assert response.status_code == 200 and len(response.json()["items"]) == 1
            tenants[alias] = response.json()["items"][0]["id"]
        root = f"/api/v1/merchant/tenants/{tenants['merchant-a']}"
        headers = tokens["merchant-a"]
        response = client.put(
            root + "/store",
            headers=headers,
            json={
                "name": "HTTP合成演示店A",
                "description": "本机隔离测试",
                "expected_version": 0,
            },
        )
        assert response.status_code == 200
        payload = {
            "customer_label": "合成电话顾客",
            "raw_text": "半斤干贝分两袋，周三自提",
            "items": [{"name": "干贝", "quantity": "0.5", "unit": "斤", "spec": "分两袋"}],
        }
        create_headers = headers | {"Idempotency-Key": "http-create-record-01"}
        response = client.post(root + "/reservations", headers=create_headers, json=payload)
        assert response.status_code == 201
        record = response.json()
        duplicate = client.post(root + "/reservations", headers=create_headers, json=payload)
        assert duplicate.status_code == 201 and duplicate.json() == record
        detail_url = root + "/reservations/" + record["id"]
        assert client.get(detail_url, headers=tokens["merchant-b"]).status_code == 404
        assert client.get(root + "/reservations", headers=tokens["merchant-b"]).status_code == 404
        assert client.get(detail_url).status_code == 401
        for target in ("CONFIRMED", "PREPARING", "READY", "COMPLETED"):
            response = client.post(
                detail_url + "/transitions",
                headers=headers
                | {
                    "Idempotency-Key": "http-state-" + target,
                },
                json={"target_status": target, "expected_version": record["version"]},
            )
            assert response.status_code == 200
            record = response.json()
            assert record["status"] == target
        detail = client.get(detail_url, headers=headers).json()
        assert len(detail["events"]) == 5
        assert detail["items"][0]["quantity"] == "0.5"
        assert detail["raw_text"] == payload["raw_text"]
        history = client.get(root + "/reservations?status=COMPLETED", headers=headers).json()
        assert history["total"] == 1 and history["items"][0]["id"] == record["id"]
        b_root = f"/api/v1/merchant/tenants/{tenants['merchant-b']}"
        assert (
            client.get(b_root + "/reservations", headers=tokens["merchant-b"]).json()["total"] == 0
        )
        print(
            "PASS real HTTP: login/store/free-text/decimal/dedup/state/history/tenant isolation",
            flush=True,
        )
        return {
            "url": detail_url,
            "headers": headers,
            "detail": detail,
            "create_url": root + "/reservations",
            "create_headers": create_headers,
            "payload": payload,
            "original": duplicate.json(),
        }


def verify_after_restart(base_url, state):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        response = client.get(state["url"], headers=state["headers"])
        assert response.status_code == 200 and response.json() == state["detail"]
        before_total = client.get(state["create_url"], headers=state["headers"]).json()["total"]
        response = client.post(
            state["create_url"], headers=state["create_headers"], json=state["payload"]
        )
        assert response.status_code == 201 and response.json() == state["original"]
        assert (
            client.get(state["create_url"], headers=state["headers"]).json()["total"]
            == before_total
        )
    print(
        "PASS real HTTP after API + PostgreSQL restart: record/events/idempotency durable",
        flush=True,
    )
