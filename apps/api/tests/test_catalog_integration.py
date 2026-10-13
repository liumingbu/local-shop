import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from local_shop.db import build_engine
from local_shop.main import create_app
from local_shop.models import Product, Tenant
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)
A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"


@pytest.fixture
def client(pg_settings):
    with TestClient(create_app(pg_settings), client=("127.0.0.1", 55001)) as app:
        app.tokens = {
            alias: app.post("/api/v1/dev/session", json={"identity": alias}).json()["access_token"]
            for alias in ("merchant-a", "merchant-b")
        }
        yield app


def base(tenant=A):
    return f"/api/v1/merchant/tenants/{tenant}"


def headers(client, alias="merchant-a", key=None):
    return {
        "Authorization": "Bearer " + client.tokens[alias],
        "Idempotency-Key": key or str(uuid4()),
    }


def category(client, tenant=A, alias="merchant-a", **extra):
    response = client.post(
        base(tenant) + "/categories",
        headers=headers(client, alias),
        json={"name": "合成分类", **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def product(client, category_id, tenant=A, alias="merchant-a", **extra):
    return client.post(
        base(tenant) + "/products",
        headers=headers(client, alias),
        json={
            "category_id": category_id,
            "name": "合成干贝",
            "unit": "斤",
            "spec": "大颗",
            "status": "PUBLISHED",
            **extra,
        },
    )


def store(client, **extra):
    return client.put(
        base() + "/store",
        headers=headers(client),
        json={"name": "合成公开店", "expected_version": 0, **extra},
    )


def update_product(client, row, **extra):
    payload = {
        key: value
        for key, value in row.items()
        if key not in ("id", "version", "price_label", "images")
    }
    return client.put(
        base() + "/products/" + row["id"],
        headers=headers(client),
        json=payload | {"expected_version": row["version"]} | extra,
    )


def test_public_store_requires_explicit_publication(client):
    assert store(client).status_code == 200
    assert client.get(f"/api/v1/stores/{A}").status_code == 404
    response = client.put(
        base() + "/store",
        headers=headers(client),
        json={
            "name": "公开店A",
            "expected_version": 1,
            "published": True,
            "public_contact": "合成营业联系方式",
            "allow_delivery": True,
        },
    )
    assert response.status_code == 200
    public = client.get(f"/api/v1/stores/{A}")
    assert public.status_code == 200
    assert public.json()["public_contact"] == "合成营业联系方式"
    assert public.json()["allow_pickup"] is False
    assert "version" not in public.json() and "internal_note" not in public.json()
    # Older clients changing only the name must not silently unpublish/config-reset the store.
    assert (
        client.put(
            base() + "/store",
            headers=headers(client),
            json={"name": "改名A", "expected_version": 2},
        ).status_code
        == 200
    )
    public = client.get(f"/api/v1/stores/{A}").json()
    assert public["name"] == "改名A" and public["allow_delivery"] is True
    assert public["public_contact"] == "合成营业联系方式"


def test_public_catalog_filters_drafts_archived_and_hides_private_fields(client):
    store(client, published=True)
    cat = category(client)
    active = product(client, cat["id"], reference_price="12.50").json()
    draft = product(client, cat["id"], status="DRAFT").json()
    archived = product(client, cat["id"], status="ARCHIVED").json()
    result = client.get(f"/api/v1/stores/{A}/products").json()
    assert result["total"] == 1 and result["items"][0]["id"] == active["id"]
    public = result["items"][0]
    assert public["reference_price"] == "12.50"
    assert (
        not {
            "actor_id",
            "internal_note",
            "customer_label",
            "version",
            "status",
            "stock",
            "amount_due",
        }
        & public.keys()
    )
    for hidden in (draft, archived):
        assert client.get(f"/api/v1/stores/{A}/products/{hidden['id']}").status_code == 404
    assert client.get(f"/api/v1/stores/{B}/products/{active['id']}").status_code == 404


def test_cross_tenant_catalog_apis(client):
    cat_a, cat_b = category(client), category(client, B, "merchant-b")
    prod = product(client, cat_a["id"]).json()
    assert product(client, cat_b["id"]).status_code == 404
    for path in ("/products", "/categories", "/products/" + prod["id"]):
        assert client.get(base() + path, headers=headers(client, "merchant-b")).status_code == 404
    assert (
        client.get(
            base(B) + "/products/" + prod["id"], headers=headers(client, "merchant-b")
        ).status_code
        == 404
    )
    assert (
        client.put(
            base(B) + "/categories/" + cat_a["id"],
            headers=headers(client, "merchant-b"),
            json={"name": "bad", "expected_version": 1},
        ).status_code
        == 404
    )
    payload = {"category_id": cat_b["id"], "name": "bad", "unit": "斤", "expected_version": 1}
    assert (
        client.put(
            base(B) + "/products/" + prod["id"], headers=headers(client, "merchant-b"), json=payload
        ).status_code
        == 404
    )
    assert client.get(base() + "/products").status_code == 401


def test_category_archival_hides_products_without_deleting(client):
    store(client, published=True)
    cat = category(client)
    prod = product(client, cat["id"]).json()
    assert (
        client.put(
            base() + "/categories/" + cat["id"],
            headers=headers(client),
            json={"name": cat["name"], "status": "ARCHIVED", "expected_version": 1},
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/stores/{A}/products").json()["total"] == 0
    assert client.get(f"/api/v1/stores/{A}/products/{prod['id']}").status_code == 404
    assert (
        client.get(base() + "/products/" + prod["id"], headers=headers(client)).status_code == 200
    )
    assert product(client, cat["id"]).status_code == 409
    assert (
        client.put(
            base() + "/categories/" + cat["id"],
            headers=headers(client),
            json={"name": cat["name"], "expected_version": 2},
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/stores/{A}/products").json()["total"] == 1


def test_product_version_concurrent_updates(client):
    row = product(client, category(client)["id"]).json()
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda name: update_product(client, row, name=name).status_code,
                ("候选甲", "候选乙"),
            )
        )
    assert sorted(results) == [200, 409]


def test_catalog_creation_idempotency(client):
    key = str(uuid4())
    data = {"name": "重复分类"}
    a = client.post(base() + "/categories", headers=headers(client, key=key), json=data)
    b = client.post(base() + "/categories", headers=headers(client, key=key), json=data)
    assert a.json() == b.json() and b.status_code == 201
    assert (
        client.post(
            base() + "/categories", headers=headers(client, key=key), json={"name": "不同"}
        ).status_code
        == 409
    )
    key = str(uuid4())
    payload = {"category_id": a.json()["id"], "name": "商品", "unit": "份"}
    a = client.post(base() + "/products", headers=headers(client, key=key), json=payload)
    b = client.post(base() + "/products", headers=headers(client, key=key), json=payload)
    assert a.json() == b.json() and b.status_code == 201


@pytest.mark.parametrize(
    "patch",
    [
        {"reference_price": "-1"},
        {"reference_price": "1.001"},
        {"reference_price": "NaN"},
        {"unit": ""},
        {"stock": 999},
        {"status": "ACTIVE"},
        {"tenant_id": B},
    ],
)
def test_catalog_rejects_invalid_fields(client, patch):
    cat = category(client)
    assert product(client, cat["id"], **patch).status_code == 422


def test_database_rejects_cross_tenant_category(client, pg_settings):
    cat = category(client, B, "merchant-b")
    engine = build_engine(pg_settings)
    try:
        with pytest.raises(IntegrityError):
            with Session(engine) as session, session.begin():
                session.add(
                    Product(tenant_id=UUID(A), category_id=UUID(cat["id"]), name="bad", unit="斤")
                )
                session.flush()
    finally:
        engine.dispose()


def test_suspension_disables_public_access(client, pg_settings):
    store(client, published=True)
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session, session.begin():
            session.get(Tenant, UUID(A)).status = "SUSPENDED"
        assert client.get(f"/api/v1/stores/{A}").status_code == 404
        assert client.get(f"/api/v1/stores/{A}/products").status_code == 404
        assert client.get(base() + "/products", headers=headers(client)).status_code == 404
    finally:
        engine.dispose()


def test_product_snapshot_survives_rename_and_archive(client):
    cat = category(client)
    prod = product(client, cat["id"], reference_price="20.50").json()
    payload = {
        "customer_label": "合成",
        "raw_text": "保留原文",
        "items": [
            {"product_id": prod["id"], "name": "客户端伪造", "unit": "错误单位", "quantity": "0.5"}
        ],
    }
    response = client.post(base() + "/reservations", headers=headers(client), json=payload)
    assert response.status_code == 201
    record = response.json()
    assert record["items"][0]["name"] == "合成干贝" and record["items"][0]["unit"] == "斤"
    assert record["items"][0]["reference_price"] == "20.50"
    assert (
        update_product(
            client, prod, name="新名称", reference_price="99", status="ARCHIVED"
        ).status_code
        == 200
    )
    detail = client.get(base() + "/reservations/" + record["id"], headers=headers(client)).json()
    assert detail["items"] == record["items"] and detail["raw_text"] == "保留原文"
    assert (
        client.post(base() + "/reservations", headers=headers(client), json=payload).status_code
        == 404
    )


def test_record_cannot_link_other_tenant_product(client):
    cat = category(client, B, "merchant-b")
    prod = product(client, cat["id"], B, "merchant-b").json()
    response = client.post(
        base() + "/reservations",
        headers=headers(client),
        json={
            "customer_label": "合成",
            "raw_text": "跨店",
            "items": [{"product_id": prod["id"], "name": "n", "unit": "斤", "quantity": "1"}],
        },
    )
    assert response.status_code == 404


def test_catalog_pagination_and_filter_scope(client):
    store(client, published=True)
    cat = category(client)
    foreign = category(client, B, "merchant-b")
    for order in (3, 1, 2):
        assert product(client, cat["id"], sort_order=order).status_code == 201
    response = client.get(f"/api/v1/stores/{A}/products?page=2&limit=2").json()
    assert response["total"] == 3 and response["items"][0]["sort_order"] == 3
    assert client.get(f"/api/v1/stores/{A}/products?category_id={foreign['id']}").status_code == 404
    assert client.get(f"/api/v1/stores/{A}/products?limit=1000").status_code == 422
