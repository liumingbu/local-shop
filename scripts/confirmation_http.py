"""Real HTTP revised details and explicit merchant-recorded re-confirmation."""

import httpx


def exercise_confirmation(base_url):
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
        response = client.post(
            f"/api/v1/stores/{tenant}/reservations",
            headers=auth["customer-a"] | {"Idempotency-Key": "http-confirm-create"},
            json={
                "raw_text": "原始要一盒",
                "privacy_accepted": True,
                "items": [{"name": "合成物品", "quantity": "1", "unit": "盒"}],
            },
        )
        assert response.status_code == 201
        original = response.json()
        root = f"/api/v1/merchant/tenants/{tenant}/reservations/{original['id']}"
        response = client.post(
            root + "/confirmation-revisions",
            headers=auth["merchant-a"] | {"Idempotency-Key": "http-confirm-proposal"},
            json={
                "expected_version": original["version"],
                "summary": "沟通后改为半斤",
                "items": [{"name": "合成物品", "quantity": "0.5", "unit": "斤"}],
                "fulfillment_at": "2026-10-15T17:00:00+08:00",
                "change_reason": "数量单位确认",
            },
        )
        assert response.status_code == 201
        pending = response.json()
        assert pending["items"] == original["items"] and pending["raw_text"] == original["raw_text"]
        assert (
            client.post(
                root + "/transitions",
                headers=auth["merchant-a"] | {"Idempotency-Key": "http-confirm-no-ack"},
                json={"target_status": "CONFIRMED", "expected_version": pending["version"]},
            ).json()["code"]
            == "EXPLICIT_RECONFIRMATION_REQUIRED"
        )
        response = client.post(
            root + "/transitions",
            headers=auth["merchant-a"] | {"Idempotency-Key": "http-confirm-explicit"},
            json={
                "target_status": "CONFIRMED",
                "expected_version": pending["version"],
                "confirmation_revision_id": pending["confirmation_revisions"][-1]["id"],
                "customer_agreed": True,
            },
        )
        assert response.status_code == 200 and response.json()["status"] == "CONFIRMED"
        mine = "/api/v1/me/records/reservation/" + original["id"]
        response = client.get(mine, headers=auth["customer-a"])
        assert response.status_code == 200
        saved = response.json()
        assert saved["confirmation_revisions"][-1]["confirmed_version"] == 3
        assert client.get(mine, headers=auth["customer-b"]).status_code == 404
        print(
            "PASS real HTTP: original request preserved/decimal revision/explicit reconfirmation",
            flush=True,
        )
        return {"url": mine, "headers": auth["customer-a"], "saved": saved}


def verify_confirmation_after_restart(base_url, state):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        response = client.get(state["url"], headers=state["headers"])
        assert response.status_code == 200 and response.json() == state["saved"]
    print(
        "PASS real HTTP after restart: original and confirmed revisions remain distinct", flush=True
    )
