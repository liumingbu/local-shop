"""Real HTTP cancellation request/decision; no mocked database or server."""

import httpx


def exercise_cancellation(base_url):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        auth = {}
        for alias in ("merchant-a", "merchant-b", "customer-a", "customer-b"):
            token = client.post("/api/v1/dev/session", json={"identity": alias}).json()[
                "access_token"
            ]
            auth[alias] = {"Authorization": "Bearer " + token}
        tenant = client.get("/api/v1/merchant/tenants", headers=auth["merchant-a"]).json()["items"][
            0
        ]["id"]
        root = f"/api/v1/merchant/tenants/{tenant}/reservations"
        response = client.post(
            f"/api/v1/stores/{tenant}/reservations",
            headers=auth["customer-a"] | {"Idempotency-Key": "http-cancel-create"},
            json={"raw_text": "HTTP合成取消申请", "privacy_accepted": True},
        )
        assert response.status_code == 201
        row = response.json()
        cancel_url = f"/api/v1/me/reservations/{row['id']}/cancellation-requests"
        body = {"expected_version": row["version"], "reason": "合成顾客不再需要"}
        request_headers = auth["customer-a"] | {"Idempotency-Key": "http-cancel-intent"}
        assert (
            client.post(
                cancel_url,
                headers=auth["customer-b"] | {"Idempotency-Key": "http-wrong-person"},
                json=body,
            ).status_code
            == 404
        )
        response = client.post(cancel_url, headers=request_headers, json=body)
        assert response.status_code == 201
        pending = response.json()
        assert pending["status"] == "PENDING_CONFIRMATION"
        assert client.post(cancel_url, headers=request_headers, json=body).json() == pending
        assert (
            client.post(
                root + f"/{row['id']}/transitions",
                headers=auth["merchant-a"] | {"Idempotency-Key": "http-block-preparation"},
                json={"expected_version": pending["version"], "target_status": "CONFIRMED"},
            ).json()["code"]
            == "CANCELLATION_REVIEW_REQUIRED"
        )
        requests = client.get(
            root + "?cancellation_pending=true", headers=auth["merchant-a"]
        ).json()
        assert row["id"] in {entry["id"] for entry in requests["items"]}
        request_id = pending["cancellation_requests"][0]["id"]
        decision_url = root + f"/{row['id']}/cancellation-requests/{request_id}/decision"
        decision_body = {
            "expected_version": pending["version"],
            "decision": "ACCEPTED",
            "response_note": "商户同意取消",
        }
        decision_headers = auth["merchant-a"] | {"Idempotency-Key": "http-cancel-decision"}
        assert (
            client.post(
                decision_url,
                headers=auth["merchant-b"] | {"Idempotency-Key": "http-wrong-shop"},
                json=decision_body,
            ).status_code
            == 404
        )
        response = client.post(decision_url, headers=decision_headers, json=decision_body)
        assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
        mine = "/api/v1/me/records/reservation/" + row["id"]
        saved = client.get(mine, headers=auth["customer-a"]).json()
        assert saved["events"][-1]["action"] == "CANCELLATION_ACCEPTED"
        print(
            "PASS real HTTP: cancellation intent/ownership/pending gate/merchant decision/audit",
            flush=True,
        )
        return {
            "url": mine,
            "auth": auth["customer-a"],
            "saved": saved,
            "decision_url": decision_url,
            "decision_body": decision_body,
            "decision_headers": decision_headers,
            "decision_result": response.json(),
        }


def verify_cancellation_after_restart(base_url, state):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        assert client.get(state["url"], headers=state["auth"]).json() == state["saved"]
        response = client.post(
            state["decision_url"], headers=state["decision_headers"], json=state["decision_body"]
        )
        assert response.status_code == 200 and response.json() == state["decision_result"]
    print(
        "PASS real HTTP after restart: cancellation decision/audit/idempotency durable", flush=True
    )
