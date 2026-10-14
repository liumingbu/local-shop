"""Daily merchant workflow against real PostgreSQL, synthetic data only."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_records_integration import B, api, base, create, headers, move

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
# Imported fixture is intentionally shared; every test receives a fresh synthetic database.
__all__ = ["api"]


def listing(api, query=""):
    response = api[0].get(base() + "/reservations" + query, headers=headers(api))
    assert response.status_code == 200, response.text
    return response.json()


def propose(api, row, when):
    result = api[0].post(
        base() + f"/reservations/{row['id']}/confirmation-revisions",
        headers=headers(api, key=str(uuid4())),
        json={
            "expected_version": row["version"],
            "summary": "合成明确承诺",
            "change_reason": "与顾客沟通",
            "fulfillment_at": when,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def agree(api, row):
    result = api[0].post(
        base() + f"/reservations/{row['id']}/transitions",
        headers=headers(api, key=str(uuid4())),
        json={
            "expected_version": row["version"],
            "target_status": "CONFIRMED",
            "customer_agreed": True,
            "confirmation_revision_id": row["confirmation_revisions"][-1]["id"],
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_date_search_number_contacts_and_literal_wildcards(api):
    row = create(
        api,
        raw_text="合成需求100%_",
        contact_name="合成人",
        contact_phone="SYNTHETIC-PHONE",
        delivery_address="合成配送地址",
        expected_at="2026-10-14T00:30:00+08:00",
    ).json()
    assert row["business_number"].startswith("LS") and row["contact_phone"] == "SYNTHETIC-PHONE"
    assert listing(api, "?day=date&on_date=2026-10-14")["total"] == 1
    assert listing(api, "?day=date&on_date=2026-10-13")["total"] == 0
    assert listing(api, "?day=none")["total"] == 0
    assert listing(api, "?q=" + row["business_number"])["total"] == 1
    assert listing(api, "?q=%25_")["total"] == 1
    assert listing(api, "?q=missing")["total"] == 0
    assert listing(api, "?method=DELIVERY")["total"] == 0
    assert api[0].get(base() + "/reservations?day=date", headers=headers(api)).status_code == 422
    assert listing(api, "?q=LS999999999999999999999999999999")["total"] == 0
    assert listing(api, "?q=LS²")["total"] == 0


def test_only_acknowledged_precise_promise_is_overdue_and_reproposal_clears(api):
    past = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    row = create(api, expected_at=past, expected_time_note="昨天之前", mark_confirmed=True).json()
    assert not row["is_overdue"] and listing(api, "?overdue=true")["total"] == 0
    row = propose(api, row, past)
    assert listing(api, "?overdue=true")["total"] == 0
    row = agree(api, row)
    assert row["is_overdue"] and listing(api, "?overdue=true")["total"] == 1
    row = propose(api, row, None)
    assert row["confirmed_due_at"] is None and not row["is_overdue"]
    row = agree(api, row)
    assert listing(api, "?overdue=true")["total"] == 0


@pytest.mark.parametrize("terminal", ["COMPLETED", "CANCELLED"])
def test_terminal_records_excluded_and_summary_is_tenant_scoped(api, terminal):
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    row = agree(api, propose(api, create(api).json(), past))
    for status in ["PREPARING", "READY", "COMPLETED"] if terminal == "COMPLETED" else ["CANCELLED"]:
        row = move(api, row, status).json()
    assert listing(api, "?overdue=true")["total"] == 0
    counts = api[0].get(base() + "/workbench-summary", headers=headers(api)).json()["counts"]
    assert counts[terminal] == 1 and counts["OVERDUE"] == 0
    assert (
        api[0].get(base() + "/workbench-summary", headers=headers(api, "merchant-b")).status_code
        == 404
    )
    assert (
        api[0]
        .get(base(B) + "/workbench-summary", headers=headers(api, "merchant-b"))
        .json()["counts"][terminal]
        == 0
    )


def test_copy_is_only_sanitized_draft_then_new_identity_and_history(api):
    row = create(
        api,
        mark_confirmed=True,
        internal_note="不复制私有内部内容",
        contact_phone="SYNTHETIC",
        items=[{"name": "合成商品", "quantity": "0.5", "unit": "斤", "spec": "散装"}],
    ).json()
    url = base() + f"/reservations/{row['id']}/copy-draft"
    result = api[0].get(url, headers=headers(api))
    assert result.status_code == 200, result.text
    draft = result.json()["draft"]
    assert draft["internal_note"] == "" and not draft["mark_confirmed"] and draft["media_ids"] == []
    assert draft["expected_at"] is None and draft["items"][0]["quantity"] == "0.5"
    assert (
        not {
            "id",
            "version",
            "customer_user_id",
            "status",
            "confirmation_revisions",
            "business_number",
        }
        & draft.keys()
    )
    assert listing(api)["total"] == 1
    fresh = api[0].post(
        base() + "/reservations", headers=headers(api, key=str(uuid4())), json=draft
    )
    assert fresh.status_code == 201, fresh.text
    assert (
        fresh.json()["id"] != row["id"]
        and fresh.json()["business_number"] != row["business_number"]
    )
    assert (
        fresh.json()["customer_user_id"] is None
        and fresh.json()["status"] == "PENDING_CONFIRMATION"
    )
    assert api[0].get(url, headers=headers(api, "merchant-b")).status_code == 404
    assert (
        api[0]
        .get(base(B) + f"/reservations/{row['id']}/copy-draft", headers=headers(api, "merchant-b"))
        .status_code
        == 404
    )


def test_date_today_tomorrow_and_no_inferred_text(api):
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    create(api, expected_at=now.isoformat())
    create(api, expected_at=(now + timedelta(days=1)).isoformat())
    create(api, expected_time_note="今天晚上")
    assert listing(api, "?day=today")["total"] == 1
    assert listing(api, "?day=tomorrow")["total"] == 1
    assert listing(api, "?day=none")["total"] == 1
    assert listing(api, "?limit=1&page=2")["total"] == 3


def test_copy_rechecks_archived_product_and_never_reuses_private_media(api):
    client = api[0]

    def post(path, body):
        result = client.post(base() + path, headers=headers(api, key=str(uuid4())), json=body)
        assert result.status_code == 201, result.text
        return result.json()

    category = post("/categories", {"name": "合成分类"})
    product = post(
        "/products",
        {
            "name": "合成旧商品",
            "category_id": category["id"],
            "unit": "斤",
            "spec": "散装",
            "status": "PUBLISHED",
        },
    )
    item = {
        "name": "旧名",
        "quantity": "0.5",
        "unit": "斤",
        "spec": "散装",
        "product_id": product["id"],
    }
    row = create(api, items=[item]).json()
    result = client.put(
        base() + f"/products/{product['id']}",
        headers=headers(api),
        json={
            "expected_version": product["version"],
            "name": "合成旧商品",
            "category_id": category["id"],
            "unit": "斤",
            "spec": "散装",
            "status": "ARCHIVED",
        },
    )
    assert result.status_code == 200, result.text
    copied = client.get(
        base() + f"/reservations/{row['id']}/copy-draft", headers=headers(api)
    ).json()
    assert copied["draft"]["items"] == [] and copied["draft"]["media_ids"] == []
    assert any("暂不可选" in warning for warning in copied["warnings"])
    assert create(api, items=[item]).status_code == 404


def test_contact_fields_only_authenticated_owner_and_merchant_never_public(api):
    client = api[0]
    response = client.put(
        base() + "/store",
        headers=headers(api),
        json={
            "name": "合成公开店",
            "expected_version": 0,
            "published": True,
            "allow_delivery": True,
        },
    )
    assert response.status_code == 200, response.text

    def customer_headers(alias):
        token = client.post("/api/v1/dev/session", json={"identity": alias}).json()["access_token"]
        return {"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid4())}

    owner = customer_headers("customer-a")
    other = customer_headers("customer-b")
    from test_records_integration import A

    response = client.post(
        f"/api/v1/stores/{A}/reservations",
        headers=owner,
        json={
            "raw_text": "合成配送需求",
            "privacy_accepted": True,
            "fulfillment_method": "DELIVERY",
            "contact_name": "合成人",
            "contact_phone": "SYNTHETIC-ONLY",
            "delivery_address": "合成地址",
        },
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["contact_phone"] == "SYNTHETIC-ONLY"
    assert row["delivery_address"] == "合成地址"
    assert "SYNTHETIC-ONLY" not in client.get(f"/api/v1/stores/{A}").text
    # Customer path is resolved by the existing contract, never by supplied phone/name.
    mine = client.get("/api/v1/me/records", headers=owner)
    assert mine.status_code == 200, mine.text
    assert row["id"] in mine.text
    theirs = client.get("/api/v1/me/records", headers=other)
    assert row["id"] not in theirs.text and "SYNTHETIC-ONLY" not in theirs.text
    assert (
        client.get(
            base() + f"/reservations/{row['id']}", headers=headers(api, "merchant-b")
        ).status_code
        == 404
    )
