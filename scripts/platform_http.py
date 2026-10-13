"""Real HTTP invitation/recipient/review/status and durable audit using synthetic users."""

import httpx


def exercise_platform(base_url):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        auth = {}
        for alias in ("platform-admin", "customer-b", "merchant-b"):
            token = client.post("/api/v1/dev/session", json={"identity": alias}).json()[
                "access_token"
            ]
            auth[alias] = {"Authorization": "Bearer " + token}
        admin, owner = auth["platform-admin"], auth["customer-b"]
        before_audit_total = client.get("/api/v1/platform/audit", headers=admin).json()["total"]
        payload = {
            "owner_user_id": "00000000-0000-4000-8000-000000000004",
            "proposed_name": "HTTP合成受邀店",
            "reason": "合成试用人工邀请",
        }
        key = {"Idempotency-Key": "platform-http-invite"}
        assert (
            client.post(
                "/api/v1/platform/invitations", headers=owner | key, json=payload
            ).status_code
            == 403
        )
        response = client.post("/api/v1/platform/invitations", headers=admin | key, json=payload)
        assert response.status_code == 201
        invited = response.json()
        assert (
            client.post("/api/v1/platform/invitations", headers=admin | key, json=payload).json()
            == invited
        )
        root = f"/api/v1/platform/invitations/{invited['id']}/review"
        assert (
            client.post(
                root,
                headers=admin | {"Idempotency-Key": "platform-http-early-review"},
                json={"expected_version": 1, "decision": "APPROVED", "reason": "合成审核"},
            ).status_code
            == 409
        )
        response = client.post(
            f"/api/v1/me/shop-invitations/{invited['id']}/response",
            headers=owner | {"Idempotency-Key": "platform-http-accept"},
            json={"expected_version": 1, "decision": "ACCEPTED"},
        )
        assert response.status_code == 200
        reviewed = client.post(
            root,
            headers=admin | {"Idempotency-Key": "platform-http-review"},
            json={"expected_version": 2, "decision": "APPROVED", "reason": "合成资质复核"},
        )
        assert reviewed.status_code == 200
        tid = reviewed.json()["tenant_id"]
        store_root = f"/api/v1/merchant/tenants/{tid}"
        assert client.get(store_root + "/store", headers=owner).json()["published"] is False
        assert client.get(f"/api/v1/stores/{tid}").status_code == 404
        response = client.put(
            store_root + "/store",
            headers=owner,
            json={
                "expected_version": 1,
                "name": "HTTP合成受邀店",
                "published": True,
                "allow_pickup": True,
            },
        )
        assert response.status_code == 200
        assert client.get(f"/api/v1/stores/{tid}").status_code == 200
        record = client.post(
            store_root + "/reservations",
            headers=owner | {"Idempotency-Key": "platform-http-manual"},
            json={"customer_label": "合成代记顾客", "raw_text": "合成受邀商户开始代记"},
        )
        assert record.status_code == 201
        assert client.get(store_root + "/reservations", headers=admin).status_code == 404
        assert (
            client.get(store_root + "/reservations", headers=auth["merchant-b"]).status_code == 404
        )
        status_root = f"/api/v1/platform/tenants/{tid}/status"
        response = client.post(
            status_root,
            headers=admin | {"Idempotency-Key": "platform-http-pause"},
            json={"expected_version": 1, "status": "SUSPENDED", "reason": "合成异常处理"},
        )
        assert response.status_code == 200
        assert client.get(store_root + "/reservations", headers=owner).status_code == 404
        assert client.get(f"/api/v1/stores/{tid}").status_code == 404
        response = client.post(
            status_root,
            headers=admin | {"Idempotency-Key": "platform-http-resume"},
            json={"expected_version": 2, "status": "ACTIVE", "reason": "合成复核恢复"},
        )
        assert response.status_code == 200
        audit = client.get("/api/v1/platform/audit", headers=admin).json()
        assert audit["total"] == before_audit_total + 5 and all(
            "response" not in x for x in audit["items"]
        )
        print(
            "PASS real HTTP: invitation/recipient consent/review/"
            "unpublished tenant/owner manual record/"
            "separate platform role/suspend/resume/audit",
            flush=True,
        )
        return {
            "admin": admin,
            "owner": owner,
            "invite": invited,
            "payload": payload,
            "key": key,
            "tenant_id": tid,
            "record_id": record.json()["id"],
            "audit": audit,
        }


def verify_platform_after_restart(base_url, state):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        assert client.get("/api/v1/platform/audit", headers=state["admin"]).json() == state["audit"]
        response = client.post(
            "/api/v1/platform/invitations",
            headers=state["admin"] | state["key"],
            json=state["payload"],
        )
        assert response.json() == state["invite"]
        root = f"/api/v1/merchant/tenants/{state['tenant_id']}/reservations/{state['record_id']}"
        assert client.get(root, headers=state["owner"]).status_code == 200
        assert client.get(root, headers=state["admin"]).status_code == 404
    print(
        "PASS real HTTP after restart: invitation identity/idempotency/status audit "
        "and separate platform scope durable",
        flush=True,
    )
