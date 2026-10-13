import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_catalog_integration import A, B, base, category, headers, product
from test_catalog_integration import client as client

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)


def body(row, **extra):
    return {
        "category_id": row["category_id"],
        "name": "合成批量修改",
        "unit": row["unit"],
        "status": row["status"],
        "expected_version": row["version"],
        **extra,
    }


def test_optional_update_key_replays_original_result_and_never_overwrites_later_version(client):
    row = product(client, category(client)["id"]).json()
    path = base() + "/products/" + row["id"]
    key = str(uuid4())
    first = client.put(path, headers=headers(client, key=key), json=body(row))
    assert first.status_code == 200 and first.json()["version"] == 2
    assert client.put(path, headers=headers(client, key=key), json=body(row)).json() == first.json()
    later = client.put(
        path, headers=headers(client), json=body(first.json(), name="后来保存的名称")
    )
    assert later.status_code == 200 and later.json()["version"] == 3
    assert client.put(path, headers=headers(client, key=key), json=body(row)).json() == first.json()
    assert client.get(path, headers=headers(client)).json()["name"] == "后来保存的名称"
    assert (
        client.put(
            path, headers=headers(client, key=key), json=body(row, name="different")
        ).status_code
        == 409
    )


def test_five_concurrent_retries_increment_version_once(client):
    row = product(client, category(client)["id"]).json()
    path = base() + "/products/" + row["id"]
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=5) as pool:
        replies = list(
            pool.map(
                lambda _: client.put(path, headers=headers(client, key=key), json=body(row)),
                range(5),
            )
        )
    assert all(x.status_code == 200 and x.json()["version"] == 2 for x in replies)
    assert client.get(path, headers=headers(client)).json()["version"] == 2


def test_update_key_does_not_bypass_tenant_or_payload_validation(client):
    row = product(client, category(client)["id"]).json()
    for tenant in [A, B]:
        assert (
            client.put(
                base(tenant) + "/products/" + row["id"],
                headers=headers(client, "merchant-b"),
                json=body(row),
            ).status_code
            == 404
        )
    assert (
        client.put(
            base() + "/products/" + row["id"],
            headers=headers(client, key="bad key"),
            json=body(row),
        ).status_code
        == 422
    )


def test_legacy_update_without_key_still_requires_exact_version(client):
    row = product(client, category(client)["id"]).json()
    auth = {"Authorization": headers(client)["Authorization"]}
    path = base() + "/products/" + row["id"]
    assert client.put(path, headers=auth, json=body(row)).status_code == 200
    assert client.put(path, headers=auth, json=body(row)).status_code == 409
