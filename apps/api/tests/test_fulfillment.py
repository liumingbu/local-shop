"""Confirmed-only sums, private exports and stale-list guards against actual PostgreSQL."""

import csv
import io
import json
import os
from uuid import uuid4

import pytest
from local_shop.db import build_engine
from local_shop.fulfillment_models import FulfillmentExport
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_records_integration import B, api, base, create, headers, move

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
__all__ = ["api"]


def product(api, name="合成品", spec="散装", unit="斤", tenant=None, alias="merchant-a"):
    root = base(tenant) if tenant else base()
    cat = api[0].post(
        root + "/categories", headers=headers(api, alias, str(uuid4())), json={"name": "合成分类"}
    )
    assert cat.status_code == 201, cat.text
    r = api[0].post(
        root + "/products",
        headers=headers(api, alias, str(uuid4())),
        json={
            "category_id": cat.json()["id"],
            "name": name,
            "spec": spec,
            "unit": unit,
            "status": "PUBLISHED",
            "supply_status": "REGULAR",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def record(api, p, quantity="0.5", **extra):
    r = create(
        api,
        mark_confirmed=True,
        items=[
            {
                "product_id": p["id"],
                "name": p["name"],
                "quantity": quantity,
                "unit": p["unit"],
                "spec": p["spec"],
            }
        ],
        **extra,
    )
    assert r.status_code == 201, r.text
    return r.json()


def listing(api, query=""):
    r = api[0].get(base() + "/fulfillment" + query, headers=headers(api))
    assert r.status_code == 200, r.text
    return r.json()


def export(api, data, key=None, **extra):
    return api[0].post(
        base() + "/fulfillment/exports",
        headers=headers(api, key=key or str(uuid4())),
        json={
            "scope": data["scope"],
            "expected_fingerprint": data["fingerprint"],
            "purpose": "PREPARATION",
            "format": "CSV",
            **extra,
        },
    )


def test_sums_trace_ids_specs_units_and_manual_exclusions(api):
    p = product(api)
    one = record(api, p)
    two = record(api, p, "1.25")
    same_name = product(api)
    three = record(api, same_name, "2")
    manual = create(api, mark_confirmed=True, raw_text="合成原文：半袋先核对").json()
    assert create(api).status_code == 201
    other = product(api, tenant=B, alias="merchant-b")
    record(api, other, tenant=B, alias="merchant-b")
    data = listing(api)
    assert data["count"] == 4 and len(data["groups"]) == 2
    group = next(g for g in data["groups"] if g["product_id"] == p["id"])
    assert group["quantity"] == "1.75" and {r["id"] for r in group["orders"]} == {
        one["id"],
        two["id"],
    }
    assert data["needs_review"][0]["id"] == manual["id"]
    assert three["id"] in {r["id"] for g in data["groups"] for r in g["orders"]}
    # Changing the product definition cannot rewrite prior confirmed snapshots.
    values = {
        k: p[k]
        for k in [
            "category_id",
            "name",
            "description",
            "unit",
            "spec",
            "reference_price",
            "supply_status",
            "status",
            "sort_order",
        ]
    }
    values.update(unit="盒", spec="礼盒", expected_version=p["version"])
    changed = api[0].put(base() + f"/products/{p['id']}", headers=headers(api), json=values)
    assert changed.status_code == 200, changed.text
    record(api, changed.json(), "3")
    data = listing(api)
    assert len(data["groups"]) == 3
    assert {(g["unit"], g["spec"]) for g in data["groups"] if g["product_id"] == p["id"]} == {
        ("斤", "散装"),
        ("盒", "礼盒"),
    }


def test_stale_cancelled_completed_and_export_never_transition(api):
    p = product(api)
    row = record(api, p)
    before = listing(api)
    updated = move(api, row, "CANCELLED")
    assert updated.status_code == 200
    assert export(api, before).status_code == 409
    data = listing(api)
    assert data["count"] == 0 and data["groups"] == []
    row = record(api, p)
    for state in ["PREPARING", "READY", "COMPLETED"]:
        r = move(api, row, state)
        assert r.status_code == 200, r.text
        row = r.json()
        if state == "READY":
            assert listing(api)["count"] == 0
            handover = listing(api, "?phase=DELIVERY")
            assert handover["count"] == 1
            assert export(api, handover, purpose="HANDOVER", format="TEXT").status_code == 200
    assert listing(api, "?phase=ACTIVE")["count"] == 0
    row = record(api, p)
    data = listing(api)
    assert export(api, data).status_code == 200
    saved = api[0].get(base() + f"/reservations/{row['id']}", headers=headers(api)).json()
    assert saved["status"] == "CONFIRMED" and saved["version"] == row["version"]


@pytest.mark.parametrize("method", ["PICKUP", "DELIVERY"])
def test_explicit_contacts_csv_text_safety_and_metadata_only_audit(api, pg_settings, method):
    p = product(api, name='=HYPERLINK("synthetic")')
    record(
        api,
        p,
        fulfillment_method=method,
        contact_name="SYNTHETIC_PERSON",
        contact_phone="SYNTHETIC_PHONE",
        delivery_address="SYNTHETIC_ADDRESS",
        internal_note="NEVER_EXPORT_INTERNAL",
        raw_text="SYNTHETIC_PHONE in raw text",
    )
    data = listing(api)
    key = str(uuid4())
    r = export(api, data, key)
    assert r.status_code == 200, r.text
    text = r.json()["content"]
    assert "SYNTHETIC_PHONE" not in text and "NEVER_EXPORT_INTERNAL" not in text
    assert all(v.startswith("'") for line in csv.reader(io.StringIO(text)) for v in line)
    assert export(api, data, key).json()["audit_id"] == r.json()["audit_id"]
    assert export(api, data, include_contact=True, contact_acknowledged=True).status_code == 422
    assert export(api, data, purpose="HANDOVER", include_contact=True).status_code == 422
    contact = export(
        api,
        data,
        purpose="HANDOVER",
        include_contact=True,
        contact_acknowledged=True,
        format="TEXT",
    )
    assert contact.status_code == 200, contact.text
    assert "SYNTHETIC_PHONE" in contact.json()["content"]
    assert ("SYNTHETIC_ADDRESS" in contact.json()["content"]) == (method == "DELIVERY")
    assert "NEVER_EXPORT_INTERNAL" not in contact.json()["content"]
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        audits = list(session.scalars(select(FulfillmentExport)))
        assert len(audits) == 2
        encoded = json.dumps([a.scope for a in audits])
        assert "SYNTHETIC" not in encoded
    engine.dispose()
    assert api[0].get(base(B) + "/fulfillment", headers=headers(api)).status_code == 404
    assert (
        api[0]
        .post(
            base(B) + "/fulfillment/exports",
            headers=headers(api, key=str(uuid4())),
            json={
                "scope": data["scope"],
                "expected_fingerprint": data["fingerprint"],
                "purpose": "HANDOVER",
            },
        )
        .status_code
        == 404
    )
    assert api[0].get(base() + "/fulfillment").status_code == 401


def test_pending_customer_cancellation_is_review_not_total(api):
    api[0].put(
        base() + "/store",
        headers=headers(api),
        json={"name": "合成店", "expected_version": 0, "published": True, "allow_pickup": True},
    )
    p = product(api)
    customer = (
        api[0].post("/api/v1/dev/session", json={"identity": "customer-a"}).json()["access_token"]
    )
    h = {"Authorization": "Bearer " + customer, "Idempotency-Key": str(uuid4())}
    row = api[0].post(
        "/api/v1/stores/10000000-0000-4000-8000-000000000001/reservations",
        headers=h,
        json={
            "raw_text": "合成顾客需求",
            "customer_label": "合成顾客",
            "privacy_accepted": True,
            "items": [
                {
                    "product_id": p["id"],
                    "quantity": "1",
                    "unit": "斤",
                    "name": p["name"],
                    "spec": p["spec"],
                }
            ],
        },
    )
    assert row.status_code == 201, row.text
    confirmed = move(api, row.json(), "CONFIRMED")
    assert confirmed.status_code == 200
    h["Idempotency-Key"] = str(uuid4())
    cancellation = api[0].post(
        "/api/v1/me/reservations/" + row.json()["id"] + "/cancellation-requests",
        headers=h,
        json={"expected_version": confirmed.json()["version"], "reason": "合成取消"},
    )
    assert cancellation.status_code == 201, cancellation.text
    data = listing(api)
    assert data["count"] == 1 and data["groups"] == []
    assert "取消意向待决定" in data["needs_review"][0]["reasons"]


def test_bounded_range_and_duplicate_lines_trace_one_order(api, pg_settings):
    from uuid import UUID

    from local_shop.models import Reservation

    p = product(api)
    item = {
        "product_id": p["id"],
        "name": p["name"],
        "spec": p["spec"],
        "unit": p["unit"],
        "quantity": "0.5",
    }
    response = create(api, mark_confirmed=True, items=[item, item])
    assert response.status_code == 201
    data = listing(api)
    assert data["groups"][0]["quantity"] == "1.0"
    assert (
        len(data["groups"][0]["orders"]) == 1
        and data["groups"][0]["orders"][0]["quantity"] == "1.0"
    )
    engine = build_engine(pg_settings)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Reservation(
                    tenant_id=UUID("10000000-0000-4000-8000-000000000001"),
                    actor_id=UUID("00000000-0000-4000-8000-000000000001"),
                    source="MERCHANT_PHONE",
                    customer_label="合成",
                    raw_text="合成范围",
                    items=[],
                    fulfillment_method="PICKUP",
                    status="CONFIRMED",
                )
                for _ in range(199)
            ]
        )
    engine.dispose()
    import time

    started = time.perf_counter()
    full = listing(api)
    assert full["count"] == 200
    print(
        "FULFILLMENT_REFERENCE confirmed_records=200 "
        f"elapsed_ms={(time.perf_counter() - started) * 1000:.2f}; real PG/TestClient only"
    )
    extra = create(api, mark_confirmed=True)
    assert extra.status_code == 201
    r = api[0].get(base() + "/fulfillment", headers=headers(api))
    assert r.status_code == 422
    assert r.json()["code"] == "NARROW_FULFILLMENT_RANGE_MAX_200"
    assert export(api, data).status_code == 422


def test_only_latest_acknowledged_revision_counts(api):
    from test_daily_workbench import agree

    p = product(api)
    row = record(api, p)
    old = listing(api)
    change = api[0].post(
        base() + f"/reservations/{row['id']}/confirmation-revisions",
        headers=headers(api, key=str(uuid4())),
        json={
            "expected_version": row["version"],
            "summary": "合成变更数量",
            "items": [
                {
                    "product_id": p["id"],
                    "name": p["name"],
                    "spec": p["spec"],
                    "unit": p["unit"],
                    "quantity": "2",
                }
            ],
            "change_reason": "已联系合成顾客",
            "fulfillment_at": "2026-10-16T01:30:00+00:00",
        },
    )
    assert change.status_code == 201, change.text
    assert listing(api)["groups"] == [] and export(api, old).status_code == 409
    agree(api, change.json())
    assert listing(api)["groups"][0]["quantity"] == "2"
    result = export(api, listing(api), purpose="HANDOVER", format="TEXT")
    assert "2026-10-16 09:30（北京时间）" in result.json()["content"]


def test_search_not_copied_into_export_scope(api):
    p = product(api)
    record(api, p, raw_text="PRIVATE_SEARCH_MARKER")
    data = listing(api, "?q=PRIVATE_SEARCH_MARKER")
    result = export(api, data)
    assert result.status_code == 200 and "PRIVATE_SEARCH_MARKER" not in result.json()["content"]
