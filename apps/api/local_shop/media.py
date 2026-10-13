"""Bounded merchant image uploads; public access only through published associations."""

import hashlib
import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .catalog import find_owned, published_store
from .image_store import MAX_UPLOAD, active_media, images_json, media_path, normalize_image
from .models import Category, MediaObject, Product, ProductMedia
from .records import StrictModel, idempotent


class ImageOrder(StrictModel):
    media_ids: list[UUID] = Field(max_length=8)
    expected_version: int = Field(ge=1)

    @field_validator("media_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate image")
        return value


class MediaStatus(StrictModel):
    status: Literal["ACTIVE", "ARCHIVED"]
    expected_version: int = Field(ge=1)


def media_json(row):
    return {
        "id": str(row.id),
        "purpose": row.purpose,
        "mime_type": row.mime_type,
        "size": row.size,
        "width": row.width,
        "height": row.height,
        "status": row.status,
        "version": row.version,
    }


def build_router(access, settings):
    router = APIRouter(prefix="/api/v1")
    database, actor, authorize, key_value = (
        access.database,
        access.actor,
        access.authorize,
        access.key_value,
    )

    def send_image(row):
        path = media_path(settings, row.id)
        if not path.is_file():
            raise HTTPException(404, "MEDIA_UNAVAILABLE")
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    @router.post("/merchant/tenants/{tenant_id}/media", status_code=201)
    async def upload(
        tenant_id: UUID,
        request: Request,
        purpose: Literal["PRODUCT", "LOGO"] = "PRODUCT",
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        await run_in_threadpool(authorize, session, tenant_id, uid)
        if request.headers.get("content-type", "").split(";", 1)[0] not in {
            "image/jpeg",
            "image/png",
            "image/webp",
        }:
            raise HTTPException(415, "UNSUPPORTED_MEDIA_TYPE")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "IMAGE_TOO_LARGE_OR_EMPTY")
            data.extend(chunk)
        raw = bytes(data)
        normalized, width, height = await run_in_threadpool(normalize_image, raw)
        payload = {"purpose": purpose, "sha256": hashlib.sha256(raw).hexdigest()}

        def persist():
            def action():
                mid = uuid4()
                path = media_path(settings, mid)
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                # Only files actually created by this transaction can be removed on rollback.
                session.info.setdefault("new_media_paths", []).append(path)
                with os.fdopen(fd, "wb") as output:
                    output.write(normalized)
                    output.flush()
                    os.fsync(output.fileno())
                row = MediaObject(
                    id=mid,
                    tenant_id=tenant_id,
                    owner_id=uid,
                    purpose=purpose,
                    storage_key=path.name,
                    size=len(normalized),
                    width=width,
                    height=height,
                    sha256=hashlib.sha256(normalized).hexdigest(),
                )
                session.add(row)
                session.flush()
                return media_json(row)

            return idempotent(session, tenant_id, uid, "upload-image", key, payload, action)

        try:
            return await run_in_threadpool(persist)
        except OSError:
            raise HTTPException(503, "MEDIA_STORAGE_UNAVAILABLE") from None

    @router.get("/merchant/tenants/{tenant_id}/media/{media_id}/content")
    def private_preview(
        tenant_id: UUID,
        media_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        return send_image(active_media(session, tenant_id, media_id))

    @router.patch("/merchant/tenants/{tenant_id}/media/{media_id}")
    def set_status(
        tenant_id: UUID,
        media_id: UUID,
        payload: MediaStatus,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        row = find_owned(session, MediaObject, tenant_id, media_id, lock=True)
        if row.version != payload.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        row.status = payload.status
        row.version += 1
        session.flush()
        return media_json(row)

    @router.put("/merchant/tenants/{tenant_id}/products/{product_id}/images")
    def order_images(
        tenant_id: UUID,
        product_id: UUID,
        payload: ImageOrder,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        product = find_owned(session, Product, tenant_id, product_id, lock=True)
        if product.version != payload.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        for mid in payload.media_ids:
            active_media(session, tenant_id, mid, "PRODUCT")
        session.execute(
            delete(ProductMedia).where(
                ProductMedia.tenant_id == tenant_id, ProductMedia.product_id == product_id
            )
        )
        for position, mid in enumerate(payload.media_ids):
            session.add(
                ProductMedia(
                    tenant_id=tenant_id, product_id=product_id, media_id=mid, sort_order=position
                )
            )
        product.version += 1
        session.flush()
        return {
            "id": str(product.id),
            "version": product.version,
            "images": images_json(session, product),
        }

    @router.get("/stores/{store_id}/products/{product_id}/images/{media_id}")
    def public_image(
        store_id: UUID,
        product_id: UUID,
        media_id: UUID,
        session: Session = Depends(database, scope="function"),
    ):
        published_store(session, store_id)
        product = session.scalar(
            select(Product)
            .join(
                Category,
                (Product.category_id == Category.id) & (Product.tenant_id == Category.tenant_id),
            )
            .where(
                Product.tenant_id == store_id,
                Product.id == product_id,
                Product.status == "PUBLISHED",
                Category.status == "ACTIVE",
            )
        )
        if product is None or session.get(ProductMedia, (store_id, product_id, media_id)) is None:
            raise HTTPException(404, "IMAGE_NOT_FOUND")
        return send_image(active_media(session, store_id, media_id, "PRODUCT"))

    @router.get("/stores/{store_id}/logo")
    def public_logo(store_id: UUID, session: Session = Depends(database, scope="function")):
        store = published_store(session, store_id)
        if store.logo_media_id is None:
            raise HTTPException(404, "IMAGE_NOT_FOUND")
        return send_image(active_media(session, store_id, store.logo_media_id, "LOGO"))

    return router
