"""Three synthetic merchant journeys over real HTTP/PG. Not a real merchant trial."""

import csv
import io
import json
import sys
from uuid import uuid4

import httpx
from local_runtime import Runtime
from PIL import Image
from platform_http import exercise_platform

A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"


def exercise_pilot(url, invited=None, *, pickup_address_minimized=True):
    invited = invited or exercise_platform(url)
    with httpx.Client(base_url=url, trust_env=False, timeout=15) as client:

        def call(path, headers=None, method="GET", body=None, key=None):
            h = dict(headers or {})
            if method == "POST":
                h["Idempotency-Key"] = key or str(uuid4())
            response = client.request(
                method, path, headers=h, json=body if body is not None else None
            )
            assert response.status_code < 300, (path, response.status_code, response.text)
            return response.json()

        def login(alias):
            return {
                "Authorization": "Bearer "
                + call("/api/v1/dev/session", method="POST", body={"identity": alias})[
                    "access_token"
                ]
            }

        owner_a, owner_b, customer = login("merchant-a"), login("merchant-b"), login("customer-a")
        stores = [
            (A, owner_a, "合成五金试点"),
            (B, owner_b, "合成散装干货试点"),
            (invited["tenant_id"], invited["owner"], "合成文字图片试点"),
        ]
        for tid, owner, name in stores:
            root = f"/api/v1/merchant/tenants/{tid}"
            r = client.get(root + "/store", headers=owner)
            version = 0 if r.status_code == 404 else r.json()["version"]
            call(
                root + "/store",
                owner,
                "PUT",
                {
                    "name": name,
                    "expected_version": version,
                    "published": True,
                    "allow_pickup": True,
                    "allow_delivery": True,
                    "delivery_note": "合成场景：先确认时间再备货",
                },
            )
            assert call(root + "/preparation", owner)["manual_record_allowed"]
        rows_by_store = {
            A: [
                ["螺丝", "合成试点分类", "M8", "盒", "", "常备", "0", "合成"],
                ["螺丝", "合成试点分类", "M10", "盒", "", "常备", "1", "合成"],
            ],
            B: [
                ["干贝", "合成试点分类", "散装", "斤", "", "待确认", "0", "合成"],
                ["干贝", "合成试点分类", "散装", "克", "", "待确认", "1", "合成"],
            ],
        }
        created = []
        for tid, owner, _ in stores[:2]:
            root = f"/api/v1/merchant/tenants/{tid}"
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(
                ["商品名称", "分类", "规格", "单位", "参考价格", "供货说明", "排序", "商品介绍"]
            )
            writer.writerows(rows_by_store[tid])
            job = call(root + "/catalog-imports", owner, "POST", {"csv_text": out.getvalue()})
            assert job["counts"]["PENDING"] == 2
            job = call(
                root + f"/catalog-imports/{job['id']}/confirm",
                owner,
                "POST",
                {
                    "expected_version": job["version"],
                    "confirmed": True,
                    "allow_new_categories": True,
                    "allow_duplicates": False,
                },
            )
            products = []
            for number in [1, 2]:
                receipt = call(
                    root + f"/catalog-imports/{job['id']}/rows/{number}",
                    owner,
                    "POST",
                    {"expected_version": job["version"]},
                )
                job = call(root + f"/catalog-imports/{job['id']}", owner)
                product = call(root + f"/products/{receipt['row']['product_id']}", owner)
                assert product["status"] == "DRAFT"
                # Explicit synthetic merchant publication is separate from CSV draft import.
                product = call(
                    root + f"/products/{product['id']}",
                    owner,
                    "PUT",
                    {
                        **{
                            k: product[k]
                            for k in [
                                "category_id",
                                "name",
                                "description",
                                "unit",
                                "spec",
                                "reference_price",
                                "supply_status",
                                "sort_order",
                            ]
                        },
                        "status": "PUBLISHED",
                        "expected_version": product["version"],
                    },
                )
                products.append(product)
            items = [
                {
                    "product_id": p["id"],
                    "name": p["name"],
                    "spec": p["spec"],
                    "unit": p["unit"],
                    "quantity": ("0.5" if n == 0 else "500") if tid == B else str(n + 1),
                }
                for n, p in enumerate(products)
            ]
            record = call(
                root + "/reservations",
                owner,
                "POST",
                {
                    "customer_label": "与合成顾客同名但不绑定",
                    "contact_phone": "SYNTHETIC_PHONE",
                    "delivery_address": "SYNTHETIC_ADDRESS",
                    "raw_text": "PILOT_" + tid,
                    "items": items,
                    "mark_confirmed": True,
                    "internal_note": "SYNTHETIC_INTERNAL",
                    "fulfillment_method": "PICKUP",
                },
            )
            created.append((tid, owner, record))
            snapshot = call(root + "/fulfillment?q=PILOT_" + tid, owner)
            assert len(snapshot["groups"]) == 2
            exported = call(
                root + "/fulfillment/exports",
                owner,
                "POST",
                {
                    "scope": {"q": "PILOT_" + tid},
                    "expected_fingerprint": snapshot["fingerprint"],
                    "purpose": "PREPARATION",
                    "format": "CSV",
                },
            )
            assert "SYNTHETIC_PHONE" not in str(exported) and "SYNTHETIC_INTERNAL" not in str(
                exported
            )
            handover = call(
                root + "/fulfillment/exports",
                owner,
                "POST",
                {
                    "scope": {"q": "PILOT_" + tid},
                    "expected_fingerprint": snapshot["fingerprint"],
                    "purpose": "HANDOVER",
                    "format": "TEXT",
                    "include_contact": True,
                    "contact_acknowledged": True,
                },
            )
            assert "SYNTHETIC_PHONE" in str(handover) and "SYNTHETIC_INTERNAL" not in str(handover)
            if pickup_address_minimized:
                assert "SYNTHETIC_ADDRESS" not in str(handover)
            draft = call(root + f"/reservations/{record['id']}/contact-draft", owner)
            assert draft["review_required"] and not draft["sent"]
            contact = call(
                root + f"/reservations/{record['id']}/contacts",
                owner,
                "POST",
                {
                    "expected_version": record["version"],
                    "method": "PHONE",
                    "note": "合成电话明确备货",
                    "confirmed": True,
                },
            )
            record["version"] = contact["record_version"]
            for status in ["PREPARING", "READY", "COMPLETED"]:
                record = call(
                    root + f"/reservations/{record['id']}/transitions",
                    owner,
                    "POST",
                    {"expected_version": record["version"], "target_status": status},
                )
            assert call(root + "/fulfillment?q=PILOT_" + tid, owner)["orders"] == []
            mine = call("/api/v1/me/records?store_id=" + tid + "&kind=reservation", customer)
            assert all(x["id"] != record["id"] for x in mine["items"])
        tid, owner, _ = stores[2]
        root = f"/api/v1/merchant/tenants/{tid}"
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "blue").save(image, "PNG")
        upload = client.post(
            f"/api/v1/stores/{tid}/private-media?privacy_accepted=true",
            headers=customer | {"Idempotency-Key": str(uuid4()), "Content-Type": "image/png"},
            content=image.getvalue(),
        )
        assert upload.status_code == 201
        inquiry = call(
            f"/api/v1/stores/{tid}/inquiries",
            customer,
            "POST",
            {
                "raw_text": "PILOT_C_TEXT 合成图片询货：请确认有没有这款",
                "privacy_accepted": True,
                "media_ids": [upload.json()["id"]],
            },
        )
        feed = call(root + "/updates", owner)
        key = next(x["event_key"] for x in feed["items"] if x["record_id"] == inquiry["id"])
        call(root + "/updates/read", owner, "POST", {"event_keys": [key]})
        reply = call(
            root + f"/inquiries/{inquiry['id']}/replies",
            owner,
            "POST",
            {
                "expected_version": inquiry["version"],
                "text": "合成答复：待核对规格，不代表备货",
                "visible_to_customer": True,
            },
        )
        assert reply["status"] == "REPLIED"
        notices = call(f"/api/v1/me/stores/{tid}/updates", customer)
        call(
            f"/api/v1/me/stores/{tid}/updates/read",
            customer,
            "POST",
            {"event_keys": [x["event_key"] for x in notices["items"]]},
        )
        current = call(root + f"/inquiries/{inquiry['id']}", owner)
        contact = call(
            root + f"/inquiries/{inquiry['id']}/contacts",
            owner,
            "POST",
            {
                "expected_version": current["version"],
                "method": "NOT_REACHED",
                "note": "合成：暂未联系上，继续待核对",
                "confirmed": True,
            },
        )
        current["version"] = contact["record_version"]
        converted = call(
            root + f"/inquiries/{inquiry['id']}/convert",
            owner,
            "POST",
            {
                "expected_version": current["version"],
                "customer_label": "合成顾客",
                "raw_text": "PILOT_C_TEXT待人工核对",
                "mark_confirmed": False,
                "source": "MERCHANT_WECHAT",
                "fulfillment_method": "PICKUP",
            },
        )
        # Conversion requires explicit intent and still does not assert confirmation.
        rid = converted["id"]
        record = call(root + f"/reservations/{rid}", owner)
        assert record["status"] == "PENDING_CONFIRMATION"
        record = call(
            root + f"/reservations/{rid}/transitions",
            owner,
            "POST",
            {"expected_version": record["version"], "target_status": "CONFIRMED"},
        )
        snapshot = call(root + "/fulfillment?q=PILOT_C_TEXT", owner)
        assert snapshot["needs_review"] and not snapshot["groups"]
        for status in ["PREPARING", "READY", "COMPLETED"]:
            record = call(
                root + f"/reservations/{rid}/transitions",
                owner,
                "POST",
                {"expected_version": record["version"], "target_status": status},
            )
        for other_tid, other_owner, _ in stores:
            for target_tid, _, row in created:
                if other_tid != target_tid:
                    assert (
                        client.get(
                            f"/api/v1/merchant/tenants/{target_tid}/reservations/{row['id']}",
                            headers=other_owner,
                        ).status_code
                        == 404
                    )
        assert client.get("/api/v1/media/" + upload.json()["id"]).status_code == 404
        private_path = f"/api/v1/me/media/{upload.json()['id']}/content?store_id={tid}"
        assert client.get(private_path).status_code == 401
        assert client.get(private_path, headers=customer).status_code == 200
        assert client.get(private_path, headers=owner_a).status_code == 404
        assert (
            client.get(root + f"/media/{upload.json()['id']}/content", headers=owner_b).status_code
            == 404
        )
        print(
            "PASS synthetic 3-store pilot: fixed-spec / fractional different units / "
            "private image-text inquiry; E import drafts, F scoped exports, "
            "G explicit reads/contacts; business completion and cross-store rejection",
            flush=True,
        )
        return {
            "tenant_id": tid,
            "event_key": key,
            "owner_id": "00000000-0000-4000-8000-000000000004",
        }


def main():
    if len(sys.argv) != 1:
        raise SystemExit("No external target arguments accepted")
    with Runtime() as runtime:
        runtime.migrate()
        runtime.seed()
        runtime.start()
        exercise_pilot(runtime.url)
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "merchants": "THREE_SYNTHETIC_ONLY",
                    "browser": "NOT_RUN",
                    "wechat_device": "NOT_RUN",
                    "production": "NOT_DEPLOYED",
                }
            )
        )


if __name__ == "__main__":
    main()
