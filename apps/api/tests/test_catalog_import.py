"""Tenant import durability and derived readiness with real PostgreSQL."""

import csv
import io
import os
from uuid import uuid4

import pytest
from test_records_integration import B, api, base, create, headers

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PG required"
)
__all__ = ["api"]
COLUMNS = ["商品名称", "分类", "规格", "单位", "参考价格", "供货说明", "排序", "商品介绍"]


def csv_text(rows):
    out = io.StringIO(newline="")
    w = csv.writer(out)
    w.writerow(COLUMNS)
    w.writerows(rows)
    return out.getvalue()


def preview(api, rows, **kwargs):
    r = api[0].post(
        base() + "/catalog-imports",
        headers=headers(api, key=str(uuid4())),
        json={"csv_text": csv_text(rows), **kwargs},
    )
    assert r.status_code == 201, r.text
    return r.json()


def confirm(api, job, duplicates=False):
    r = api[0].post(
        base() + f"/catalog-imports/{job['id']}/confirm",
        headers=headers(api, key=str(uuid4())),
        json={
            "expected_version": job["version"],
            "confirmed": True,
            "allow_new_categories": True,
            "allow_duplicates": duplicates,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def apply(api, job, number, key=None):
    return api[0].post(
        base() + f"/catalog-imports/{job['id']}/rows/{number}",
        headers=headers(api, key=key or str(uuid4())),
        json={"expected_version": job["version"]},
    )


def test_zero_catalog_preparation_and_manual_record(api):
    p = api[0].get(base() + "/preparation", headers=headers(api))
    assert p.status_code == 200, p.text
    assert p.json()["product_count"] == 0 and p.json()["manual_record_allowed"]
    assert create(api).status_code == 201
    r = api[0].put(
        base() + "/store",
        headers=headers(api),
        json={
            "name": "合成五金店",
            "public_contact": "合成店内联系",
            "public_address": "合成自提地点",
            "delivery_note": "提前确认自提",
            "allow_pickup": True,
            "expected_version": 0,
        },
    )
    assert r.status_code == 200, r.text
    p = api[0].get(base() + "/preparation", headers=headers(api)).json()
    assert p["steps"][0]["complete"] and p["steps"][2]["complete"]
    assert not p["steps"][-1]["complete"] and p["product_count"] == 0
    assert api[0].get(base(B) + "/preparation", headers=headers(api)).status_code == 404


def test_csv_quotes_newline_empty_price_specs_and_resume(api):
    job = preview(
        api,
        [
            ["茶,叶", "茶叶", "散装", "斤", "", "待确认", "0", '含"引号"\n两行'],
            ["茶,叶", "茶叶", "礼盒", "盒", "12.50", "常备", "1", "合成"],
            ["无效", "茶叶", "", "", "1", "常备", "0", ""],
        ],
    )
    assert job["counts"] == {"PENDING": 2, "INVALID": 1, "FAILED": 0, "SUCCESS": 0}
    assert job["new_categories"] == ["茶叶"] and not any(r["warnings"] for r in job["rows"])
    assert api[0].get(base() + "/products", headers=headers(api)).json()["total"] == 0
    assert apply(api, job, 1).status_code == 422
    job = confirm(api, job)
    key = str(uuid4())
    r = apply(api, job, 1, key)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["row"]["state"] == "SUCCESS"
    assert apply(api, job, 1, key).json() == first
    # Simulate client reload: re-read the persisted task, then continue only missing rows.
    job = api[0].get(base() + f"/catalog-imports/{job['id']}", headers=headers(api)).json()
    r = apply(api, job, 2)
    assert r.status_code == 200, r.text
    assert r.json()["row"]["state"] == "SUCCESS"
    assert (
        apply(api, job, 1).status_code == 200
    )  # fresh key cannot duplicate an already successful row
    products = api[0].get(base() + "/products", headers=headers(api)).json()["items"]
    assert len(products) == 2 and {p["status"] for p in products} == {"DRAFT"}
    assert any(p["reference_price"] is None for p in products)
    assert len(api[0].get(base() + "/categories", headers=headers(api)).json()["items"]) == 1


def test_duplicate_batches_require_explicit_choice_and_no_overwrite(api):
    rows = [["合成螺钉", "五金", "M6", "盒", "", "常备", "0", ""]]
    j = confirm(api, preview(api, rows))
    assert apply(api, j, 1).status_code == 200
    j = preview(api, rows)
    assert j["rows"][0]["warnings"]
    r = api[0].post(
        base() + f"/catalog-imports/{j['id']}/confirm",
        headers=headers(api, key=str(uuid4())),
        json={"expected_version": j["version"], "confirmed": True, "allow_new_categories": True},
    )
    assert r.status_code == 422
    j = confirm(api, j, True)
    assert apply(api, j, 1).status_code == 200
    assert api[0].get(base() + "/products", headers=headers(api)).json()["total"] == 2


def test_job_paths_errors_and_apply_are_tenant_authorized(api):
    j = preview(
        api,
        [
            [
                '=HYPERLINK("x")',
                "分类",
                "规格",
                "袋",
                "",
                "常备",
                "0",
                "<script>not executable</script>",
            ]
        ],
    )
    for suffix in ["", "/errors"]:
        assert (
            api[0]
            .get(
                base(B) + f"/catalog-imports/{j['id']}" + suffix, headers=headers(api, "merchant-b")
            )
            .status_code
            == 404
        )
    assert (
        api[0]
        .post(
            base(B) + f"/catalog-imports/{j['id']}/rows/1",
            headers=headers(api, "merchant-b", str(uuid4())),
            json={"expected_version": 1},
        )
        .status_code
        == 404
    )
    assert api[0].get(base() + "/catalog-imports").status_code == 401
    output = (
        api[0]
        .get(base() + f"/catalog-imports/{j['id']}/errors", headers=headers(api))
        .json()["csv"]
    )
    values = list(csv.reader(io.StringIO(output)))
    assert all(value.startswith("'") for row in values for value in row)
    assert values[1][3].startswith("'=HYPERLINK")
    r = api[0].post(
        base() + "/catalog-imports",
        headers=headers(api, key=str(uuid4())),
        json={"csv_text": csv_text([["x", "y", "", "件", "", "常备", "0", ""]]), "tenant_id": B},
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "text,status",
    [
        (csv_text([["x", "y", "", "件", "", "常备", "0", ""]] * 201), 413),
        ("x" * 524289, 422),
        (",".join(COLUMNS) + '\n"unterminated', 422),
        (",".join(COLUMNS) + "\na,b,c,d,e,f,g,h,i", 422),
        (",".join(COLUMNS) + "\n" + "x" * 4001 + ",b,c,d,e,f,g,h", 422),
        ("tenant_id,name\na,b", 422),
        ("a\x00b", 422),
    ],
    ids=["rows", "bytes", "syntax", "columns", "cell", "headers", "control"],
)
def test_invalid_limits_never_change_products(api, text, status):
    r = api[0].post(
        base() + "/catalog-imports", headers=headers(api, key=str(uuid4())), json={"csv_text": text}
    )
    assert r.status_code == status, r.text
    assert api[0].get(base() + "/products", headers=headers(api)).json()["total"] == 0


def test_concurrent_same_row_and_new_duplicate_after_preview(api):
    from concurrent.futures import ThreadPoolExecutor

    rows = [["合成称重", "干货", "散装", "斤", "", "待确认", "0", ""]]
    job = confirm(api, preview(api, rows))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: apply(api, job, 1), range(2)))
    assert [r.status_code for r in outcomes] == [200, 200]
    assert len({r.json()["row"]["product_id"] for r in outcomes}) == 1
    assert api[0].get(base() + "/products", headers=headers(api)).json()["total"] == 1
    # A later job is checked again at execution, not merely at its preview.
    other_rows = [["合成新商品", "干货", "袋装", "袋", "", "常备", "0", ""]]
    first = confirm(api, preview(api, other_rows))
    second = confirm(api, preview(api, other_rows))
    assert apply(api, first, 1).json()["row"]["state"] == "SUCCESS"
    result = apply(api, second, 1)
    assert result.json()["row"]["state"] == "FAILED"
    saved = api[0].get(base() + f"/catalog-imports/{second['id']}", headers=headers(api)).json()
    assert saved["counts"]["FAILED"] == 1
    assert api[0].get(base() + "/products", headers=headers(api)).json()["total"] == 2


def test_maximum_200_rows_is_bounded_and_row_receipts_remain_small(api, pg_settings):
    import time

    from local_shop.db import build_engine
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    rows = [
        [f"合成品{i}", "合成分类", f"规格{i}", "件", "", "常备", str(i), "合成介绍" * 20]
        for i in range(200)
    ]
    start = time.perf_counter()
    job = confirm(api, preview(api, rows))
    times = []
    for number in range(1, 201):
        before = time.perf_counter()
        response = apply(api, job, number)
        times.append(time.perf_counter() - before)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["row"]["state"] == "SUCCESS"
        job["version"] = value["version"]
    elapsed = time.perf_counter() - start
    engine = build_engine(pg_settings)
    with Session(engine) as session:
        largest = session.scalar(
            text(
                "SELECT max(pg_column_size(response)) FROM idempotency_keys "
                "WHERE endpoint LIKE 'catalog-import-row:%'"
            )
        )
    engine.dispose()
    assert largest < 2048, largest
    saved = api[0].get(base() + f"/catalog-imports/{job['id']}", headers=headers(api)).json()
    assert saved["counts"]["SUCCESS"] == 200
    print(
        f"CSV_REFERENCE rows=200 total_seconds={elapsed:.3f} "
        f"row_p95_ms={sorted(times)[189] * 1000:.2f} largest_receipt_bytes={largest}; "
        "synthetic TestClient/real PG, not production capacity"
    )
