"""Tenant catalog commands and deliberately whitelisted public store reads."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .image_store import images_json
from .models import Category, MediaObject, Product, Store, Tenant
from .records import StrictModel, idempotent, store_json


class CategoryInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=100000)
    status: Literal["ACTIVE", "ARCHIVED"] = "ACTIVE"


class CategoryUpdate(CategoryInput):
    expected_version: int = Field(ge=1)


class ProductInput(StrictModel):
    category_id: UUID
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    unit: str = Field(min_length=1, max_length=20)
    spec: str = Field(default="", max_length=120)
    reference_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    supply_status: Literal["REGULAR", "CONFIRM", "UNAVAILABLE"] = "CONFIRM"
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = "DRAFT"
    sort_order: int = Field(default=0, ge=0, le=100000)


class ProductUpdate(ProductInput):
    expected_version: int = Field(ge=1)


def category_json(row, public=False):
    value = {"id": str(row.id), "name": row.name, "sort_order": row.sort_order}
    if not public:
        value |= {"status": row.status, "version": row.version}
    return value


def product_json(row, session, public=False):
    value = {
        "id": str(row.id),
        "category_id": str(row.category_id),
        "name": row.name,
        "description": row.description,
        "unit": row.unit,
        "spec": row.spec,
        "reference_price": str(row.reference_price) if row.reference_price is not None else None,
        "price_label": "参考价格，具体供货请联系商家确认",
        "supply_status": row.supply_status,
        "sort_order": row.sort_order,
    }
    value["images"] = images_json(session, row, public=public)
    if not public:
        value |= {"status": row.status, "version": row.version}
    return value


def find_owned(session, model, tenant_id, object_id, lock=False):
    query = select(model).where(model.tenant_id == tenant_id, model.id == object_id)
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    return row


def published_store(session, tenant_id):
    row = session.scalar(
        select(Store)
        .join(Tenant)
        .where(Store.tenant_id == tenant_id, Store.published.is_(True), Tenant.status == "ACTIVE")
    )
    if row is None:
        raise HTTPException(404, "STORE_NOT_FOUND")
    return row


def build_router(access):
    router = APIRouter(prefix="/api/v1")
    database, actor, authorize, key_value = (
        access.database,
        access.actor,
        access.authorize,
        access.key_value,
    )

    @router.post("/merchant/tenants/{tenant_id}/categories", status_code=201)
    def create_category(
        tenant_id: UUID,
        payload: CategoryInput,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            row = Category(tenant_id=tenant_id, **payload.model_dump())
            session.add(row)
            session.flush()
            return category_json(row)

        return idempotent(
            session, tenant_id, uid, "create-category", key, payload.model_dump(mode="json"), action
        )

    @router.put("/merchant/tenants/{tenant_id}/categories/{category_id}")
    def update_category(
        tenant_id: UUID,
        category_id: UUID,
        payload: CategoryUpdate,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        row = find_owned(session, Category, tenant_id, category_id, lock=True)
        if row.version != payload.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        for name, value in payload.model_dump(exclude={"expected_version"}).items():
            setattr(row, name, value)
        row.version += 1
        session.flush()
        return category_json(row)

    @router.get("/merchant/tenants/{tenant_id}/categories")
    def list_categories(
        tenant_id: UUID,
        page: int = Query(1, ge=1),
        limit: int = Query(100, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        query = select(Category).where(Category.tenant_id == tenant_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(Category.sort_order, Category.id).offset((page - 1) * limit).limit(limit)
        )
        return {
            "items": [category_json(row) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    def category_check(session, tenant_id, category_id, status):
        category = find_owned(session, Category, tenant_id, category_id)
        if category.status != "ACTIVE" and status == "PUBLISHED":
            raise HTTPException(409, "CATEGORY_ARCHIVED")

    @router.post("/merchant/tenants/{tenant_id}/products", status_code=201)
    def create_product(
        tenant_id: UUID,
        payload: ProductInput,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            category_check(session, tenant_id, payload.category_id, payload.status)
            row = Product(tenant_id=tenant_id, **payload.model_dump())
            session.add(row)
            session.flush()
            return product_json(row, session)

        return idempotent(
            session, tenant_id, uid, "create-product", key, payload.model_dump(mode="json"), action
        )

    @router.put("/merchant/tenants/{tenant_id}/products/{product_id}")
    def update_product(
        tenant_id: UUID,
        product_id: UUID,
        payload: ProductUpdate,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        row = find_owned(session, Product, tenant_id, product_id, lock=True)
        if row.version != payload.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        category_check(session, tenant_id, payload.category_id, payload.status)
        for name, value in payload.model_dump(exclude={"expected_version"}).items():
            setattr(row, name, value)
        row.version += 1
        session.flush()
        return product_json(row, session)

    @router.get("/merchant/tenants/{tenant_id}/products/{product_id}")
    def get_product(
        tenant_id: UUID,
        product_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        return product_json(find_owned(session, Product, tenant_id, product_id), session)

    @router.get("/merchant/tenants/{tenant_id}/products")
    def list_products(
        tenant_id: UUID,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        category_id: UUID | None = None,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        query = select(Product).where(Product.tenant_id == tenant_id)
        if category_id:
            find_owned(session, Category, tenant_id, category_id)
            query = query.where(Product.category_id == category_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(Product.sort_order, Product.id).offset((page - 1) * limit).limit(limit)
        )
        return {
            "items": [product_json(row, session) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @router.get("/stores/{store_id}")
    def public_store(store_id: UUID, session: Session = Depends(database, scope="function")):
        store = published_store(session, store_id)
        value = store_json(store)
        for key in ("version", "published", "logo_media_id"):
            value.pop(key)
        logo = session.get(MediaObject, store.logo_media_id) if store.logo_media_id else None
        value["logo_url"] = (
            f"/api/v1/stores/{store_id}/logo"
            if logo and logo.status == "ACTIVE" and logo.purpose == "LOGO"
            else None
        )
        rows = session.scalars(
            select(Category)
            .where(Category.tenant_id == store_id, Category.status == "ACTIVE")
            .order_by(Category.sort_order, Category.id)
            .limit(100)
        )
        return value | {"categories": [category_json(row, public=True) for row in rows]}

    def public_products_query(store_id):
        return (
            select(Product)
            .join(
                Category,
                (Product.category_id == Category.id) & (Product.tenant_id == Category.tenant_id),
            )
            .where(
                Product.tenant_id == store_id,
                Product.status == "PUBLISHED",
                Category.status == "ACTIVE",
            )
        )

    @router.get("/stores/{store_id}/products")
    def public_products(
        store_id: UUID,
        category_id: UUID | None = None,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        session: Session = Depends(database, scope="function"),
    ):
        published_store(session, store_id)
        query = public_products_query(store_id)
        if category_id:
            category = find_owned(session, Category, store_id, category_id)
            if category.status != "ACTIVE":
                raise HTTPException(404, "CATEGORY_NOT_FOUND")
            query = query.where(Product.category_id == category_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(Product.sort_order, Product.id).offset((page - 1) * limit).limit(limit)
        )
        return {
            "items": [product_json(row, session, public=True) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @router.get("/stores/{store_id}/products/{product_id}")
    def public_product(
        store_id: UUID, product_id: UUID, session: Session = Depends(database, scope="function")
    ):
        published_store(session, store_id)
        row = session.scalar(public_products_query(store_id).where(Product.id == product_id))
        if row is None:
            raise HTTPException(404, "PRODUCT_NOT_FOUND")
        return product_json(row, session, public=True)

    return router
