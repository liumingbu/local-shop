"""Actual HTTP customer inquiry, ownership, explicit conversion and history checks."""

import httpx


def exercise_customer(base_url):
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
        store = client.get(root + "/store", headers=auth["merchant-a"]).json()
        assert (
            client.put(
                root + "/store",
                headers=auth["merchant-a"],
                json={
                    "name": store["name"],
                    "expected_version": store["version"],
                    "allow_pickup": True,
                },
            ).status_code
            == 200
        )
        payload = {"raw_text": "HTTP合成顾客询货，有货吗？", "privacy_accepted": True}
        response = client.post(
            f"/api/v1/stores/{tenant}/inquiries",
            headers=auth["customer-a"] | {"Idempotency-Key": "http-customer-inquiry"},
            json=payload,
        )
        assert response.status_code == 201
        inquiry = response.json()
        path = root + "/inquiries/" + inquiry["id"]
        count_before = client.get(root + "/reservations", headers=auth["merchant-a"]).json()[
            "total"
        ]
        for visible, message, key in (
            (False, "内部测试备注", "internal"),
            (True, "合成公开答复", "public"),
        ):
            response = client.post(
                path + "/replies",
                headers=auth["merchant-a"] | {"Idempotency-Key": "http-reply-" + key},
                json={
                    "text": message,
                    "visible_to_customer": visible,
                    "expected_version": inquiry["version"],
                },
            )
            assert response.status_code == 201
            inquiry = response.json()
        assert (
            client.get(root + "/reservations", headers=auth["merchant-a"]).json()["total"]
            == count_before
        )
        response = client.get(
            "/api/v1/me/records/inquiry/" + inquiry["id"], headers=auth["customer-a"]
        )
        assert response.status_code == 200 and "内部测试备注" not in response.text
        assert len(response.json()["replies"]) == 1
        response = client.post(
            path + "/convert",
            headers=auth["merchant-a"] | {"Idempotency-Key": "http-explicit-conversion"},
            json={
                "customer_label": "合成顾客",
                "raw_text": "明确确认需求摘要",
                "expected_version": inquiry["version"],
            },
        )
        assert response.status_code == 201 and response.json()["status"] == "PENDING_CONFIRMATION"
        record = response.json()
        mine_url = "/api/v1/me/records/reservation/" + record["id"]
        response = client.get(mine_url, headers=auth["customer-a"])
        assert response.status_code == 200 and response.json()["raw_text"] == payload["raw_text"]
        assert response.json()["confirmed_text"] == "明确确认需求摘要"
        assert "internal_note" not in response.json() and "actor_id" not in response.json()
        assert client.get(mine_url, headers=auth["customer-b"]).status_code == 404
        assert client.get("/api/v1/me/records", headers=auth["customer-b"]).json()["total"] == 0
        state = {"url": mine_url, "headers": auth["customer-a"], "record": response.json()}
        response = client.post(
            f"/api/v1/stores/{tenant}/reservations",
            headers=auth["customer-a"] | {"Idempotency-Key": "http-customer-request"},
            json={"raw_text": "HTTP顾客直接登记", "privacy_accepted": True},
        )
        assert response.status_code == 201
        print(
            "PASS real HTTP: customer ownership/inquiry/reply privacy/conversion/request",
            flush=True,
        )
        return state


def verify_customer_after_restart(base_url, state):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        response = client.get(state["url"], headers=state["headers"])
        assert response.status_code == 200 and response.json() == state["record"]
    print(
        "PASS real HTTP after restart: customer ownership and original/confirmed text durable",
        flush=True,
    )
