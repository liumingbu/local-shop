"""Derived preparation and durable CSV-to-draft import. No second registration workflow."""

import copy
import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .catalog import ProductInput, find_owned
from .csv_core import HEADERS, display_csv, parse_csv
from .import_models import CatalogImport
from .models import Category, Product, Store
from .records import StrictModel, idempotent, lock_scope, store_json


class Preview(StrictModel):
    csv_text: str = Field(min_length=1, max_length=524288)


class Confirm(StrictModel):
    expected_version: int = Field(ge=1)
    confirmed: bool
    allow_new_categories: bool = False
    allow_duplicates: bool = False


class ApplyRow(StrictModel):
    expected_version: int = Field(ge=1)


def result(job):
    return {
        "id": str(job.id),
        "tenant_id": str(job.tenant_id),
        "version": job.version,
        "status": job.status,
        "rows": job.rows,
        "new_categories": job.new_categories,
        "allow_new_categories": job.allow_new_categories,
        "allow_duplicates": job.allow_duplicates,
        "created_at": job.created_at.isoformat(),
        "counts": {
            state: sum(r["state"] == state for r in job.rows)
            for state in ["PENDING", "INVALID", "FAILED", "SUCCESS"]
        },
    }


def duplicates(session, tenant, data):
    return session.scalar(
        select(func.count())
        .select_from(Product)
        .where(
            Product.tenant_id == tenant,
            Product.name == data["name"],
            Product.spec == data["spec"],
            Product.unit == data["unit"],
        )
    )


def build_router(access, settings):
    router = APIRouter(prefix="/api/v1/merchant/tenants/{tenant_id}")
    database, actor, authorize = access.database, access.actor, access.authorize

    @router.get("/preparation")
    def preparation(
        tenant_id: UUID, uid=Depends(actor), session: Session = Depends(database, scope="function")
    ):
        authorize(session, tenant_id, uid)
        store = session.get(Store, tenant_id)
        products = session.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.tenant_id == tenant_id, Product.status != "ARCHIVED")
        )
        categories = session.scalar(
            select(func.count())
            .select_from(Category)
            .where(Category.tenant_id == tenant_id, Category.status == "ACTIVE")
        )
        return {
            "store": store_json(store) if store else None,
            "steps": [
                {
                    "id": "profile",
                    "label": "店铺资料",
                    "complete": bool(
                        store and store.name and store.public_contact and store.public_address
                    ),
                },
                {
                    "id": "catalog",
                    "label": "分类/商品（可稍后完善）",
                    "complete": bool(products),
                    "optional": True,
                },
                {
                    "id": "delivery",
                    "label": "自提/配送说明",
                    "complete": bool(
                        store
                        and (store.allow_pickup or store.allow_delivery)
                        and store.delivery_note
                    ),
                },
                {"id": "preview", "label": "店内预览", "complete": bool(store)},
                {
                    "id": "share",
                    "label": "真实微信分享待接入",
                    "complete": False,
                    "external": "NOT_VERIFIED",
                },
            ],
            "preview_products": [
                {
                    "name": p.name,
                    "spec": p.spec,
                    "unit": p.unit,
                    "status": p.status,
                    "reference_price": str(p.reference_price)
                    if p.reference_price is not None
                    else None,
                }
                for p in session.scalars(
                    select(Product)
                    .where(Product.tenant_id == tenant_id, Product.status != "ARCHIVED")
                    .order_by(Product.sort_order, Product.id)
                    .limit(20)
                )
            ],
            "product_count": products,
            "category_count": categories,
            "manual_record_allowed": True,
            "notice": "没有商品库也可先记单；店内预览不表示已发布或微信分享已验收。",
        }

    @router.get("/catalog-imports/template")
    def template(
        tenant_id: UUID, uid=Depends(actor), session: Session = Depends(database, scope="function")
    ):
        authorize(session, tenant_id, uid)
        return {
            "columns": HEADERS,
            "max_rows": 200,
            "max_bytes": settings.csv_import_max_bytes,
            "csv": ",".join(HEADERS)
            + (
                "\r\n合成茶叶,茶叶,散装,斤,,待确认,0,按需确认规格\r\n"
                "合成干货,干货,小袋,袋,,常备,1,按实际供货说明\r\n"
                "合成螺钉,五金,M6,盒,,常备,2,规格先核对\r\n"
            ),
            "note": "UTF-8 CSV；供货说明仅常备/待确认/暂缺；参考价可空，默认仅草稿。",
        }

    @router.post("/catalog-imports", status_code=201)
    def preview(
        tenant_id: UUID,
        payload: Preview,
        key=Depends(access.key_value),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            rows = parse_csv(payload.csv_text, settings.csv_import_max_bytes)
            names = {r["data"]["category_name"] for r in rows if r["state"] == "PENDING"}
            existing = set(
                session.scalars(
                    select(Category.name).where(
                        Category.tenant_id == tenant_id,
                        Category.status == "ACTIVE",
                        Category.name.in_(names),
                    )
                )
            )
            seen = set()
            for row in rows:
                if row["state"] != "PENDING":
                    continue
                data = row["data"]
                signature = (data["name"], data["spec"], data["unit"])
                if signature in seen or duplicates(session, tenant_id, data):
                    row["warnings"].append("疑似重复：同名、规格、单位；需明确允许新增，绝不覆盖")
                seen.add(signature)
            job = CatalogImport(
                tenant_id=tenant_id,
                actor_id=uid,
                rows=rows,
                new_categories=sorted(names - existing),
                source_hash=hashlib.sha256(payload.csv_text.encode()).hexdigest(),
            )
            session.add(job)
            session.flush()
            return result(job)

        return idempotent(
            session, tenant_id, uid, "catalog-import-preview", key, payload.model_dump(), action
        )

    @router.get("/catalog-imports")
    def listing(
        tenant_id: UUID,
        page: int = Query(1, ge=1),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        rows = session.scalars(
            select(CatalogImport)
            .where(CatalogImport.tenant_id == tenant_id)
            .order_by(CatalogImport.created_at.desc(), CatalogImport.id)
            .offset((page - 1) * 20)
            .limit(20)
        )
        return {
            "items": [
                {
                    "id": str(j.id),
                    "status": j.status,
                    "created_at": j.created_at.isoformat(),
                    "counts": result(j)["counts"],
                }
                for j in rows
            ],
            "page": page,
        }

    @router.get("/catalog-imports/{job_id}")
    def get_job(
        tenant_id: UUID,
        job_id: UUID,
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        return result(find_owned(session, CatalogImport, tenant_id, job_id))

    @router.post("/catalog-imports/{job_id}/confirm")
    def confirm(
        tenant_id: UUID,
        job_id: UUID,
        payload: Confirm,
        key=Depends(access.key_value),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            job = find_owned(session, CatalogImport, tenant_id, job_id, lock=True)
            if job.version != payload.expected_version or job.status != "PREVIEW":
                raise HTTPException(409, "VERSION_CONFLICT")
            if not payload.confirmed:
                raise HTTPException(422, "EXPLICIT_CONFIRMATION_REQUIRED")
            if job.new_categories and not payload.allow_new_categories:
                raise HTTPException(422, "NEW_CATEGORIES_REQUIRE_CONFIRMATION")
            if any(r["warnings"] for r in job.rows) and not payload.allow_duplicates:
                raise HTTPException(422, "DUPLICATES_REQUIRE_CONFIRMATION")
            job.allow_new_categories = payload.allow_new_categories
            job.allow_duplicates = payload.allow_duplicates
            job.status = "CONFIRMED"
            job.version += 1
            session.flush()
            return result(job)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"catalog-import-confirm:{job_id}",
            key,
            payload.model_dump(),
            action,
        )

    @router.post("/catalog-imports/{job_id}/rows/{number}")
    def apply(
        tenant_id: UUID,
        job_id: UUID,
        number: int,
        payload: ApplyRow,
        key=Depends(access.key_value),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            job = find_owned(session, CatalogImport, tenant_id, job_id, lock=True)
            if number < 1 or number > len(job.rows):
                raise HTTPException(404, "ROW_NOT_FOUND")
            row = copy.deepcopy(job.rows[number - 1])
            if row["state"] == "SUCCESS":
                return {
                    "version": job.version,
                    "row": {k: row[k] for k in ("number", "state", "error", "product_id")},
                }
            if job.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            if job.status != "CONFIRMED" or row["state"] == "INVALID":
                raise HTTPException(422, "ROW_NOT_CONFIRMED_OR_INVALID")
            data = row["data"]
            lock_scope(session, f"catalog-import:{tenant_id}")

            def fail(message):
                row["state"] = "FAILED"
                row["error"] = message

            if duplicates(session, tenant_id, data) and not job.allow_duplicates:
                fail("当前已有同名同规格同单位商品；请重新预览并明确允许重复，或跳过此行")
            else:
                categories = list(
                    session.scalars(
                        select(Category)
                        .where(
                            Category.tenant_id == tenant_id,
                            Category.name == data["category_name"],
                            Category.status == "ACTIVE",
                        )
                        .limit(2)
                    )
                )
                if len(categories) > 1:
                    fail("存在多个同名有效分类，请先核对分类后重试")
                elif not categories and not job.allow_new_categories:
                    fail("分类现已不可用；请重新预览确认新分类")
                else:
                    if categories:
                        category = categories[0]
                    else:
                        category = Category(tenant_id=tenant_id, name=data["category_name"])
                        session.add(category)
                        session.flush()
                    product_data = ProductInput(
                        category_id=category.id,
                        **{k: v for k, v in data.items() if k != "category_name"},
                    )
                    product = Product(tenant_id=tenant_id, **product_data.model_dump())
                    session.add(product)
                    session.flush()
                    row.update(state="SUCCESS", error="", product_id=str(product.id))
            rows = copy.deepcopy(job.rows)
            rows[number - 1] = row
            job.rows = rows
            job.version += 1
            session.flush()
            return {
                "version": job.version,
                "row": {k: row[k] for k in ("number", "state", "error", "product_id")},
            }

        return idempotent(
            session,
            tenant_id,
            uid,
            f"catalog-import-row:{job_id}:{number}",
            key,
            payload.model_dump(),
            action,
        )

    @router.get("/catalog-imports/{job_id}/errors")
    def errors(
        tenant_id: UUID,
        job_id: UUID,
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        job = find_owned(session, CatalogImport, tenant_id, job_id)
        return {
            "csv": display_csv(
                [["行号", "状态", "错误", *HEADERS]]
                + [
                    [r["number"], r["state"], r["error"], *r["source"]]
                    for r in job.rows
                    if r["state"] != "SUCCESS"
                ]
            ),
            "note": (
                "显示用文本CSV，字段加单引号并双引号转义；请以文本列导入，"
                "勿移除保护或另存后执行公式。不是可直接重导模板。"
            ),
        }

    return router
