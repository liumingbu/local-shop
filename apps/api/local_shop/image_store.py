"""Decode/re-encode bounded images; only generated keys address local storage."""

import asyncio
import io
import warnings
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from starlette.requests import ClientDisconnect

from .models import MediaObject, ProductMedia

MAX_UPLOAD = 2 * 1024 * 1024
MAX_PIXELS = 12_000_000


async def read_bounded_image(request, timeout_seconds):
    """Total body receipt deadline, not reset on each slow chunk."""
    declared = request.headers.get("content-length")
    if declared is not None:
        if not declared.isascii() or not declared.isdigit():
            raise HTTPException(400, "INVALID_CONTENT_LENGTH")
        if len(declared) > 10 or int(declared) > MAX_UPLOAD:
            raise HTTPException(413, "IMAGE_TOO_LARGE_OR_EMPTY")
    data = bytearray()
    try:
        async with asyncio.timeout(timeout_seconds):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_UPLOAD:
                    raise HTTPException(413, "IMAGE_TOO_LARGE_OR_EMPTY")
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, "IMAGE_UPLOAD_TIMEOUT") from None
    except ClientDisconnect:
        raise HTTPException(400, "IMAGE_UPLOAD_INTERRUPTED") from None
    return bytes(data)


def normalize_image(content):
    if not content or len(content) > MAX_UPLOAD:
        raise HTTPException(413, "IMAGE_TOO_LARGE_OR_EMPTY")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content), formats=["JPEG", "PNG", "WEBP"]) as original:
                if (
                    original.width * original.height > MAX_PIXELS
                    or getattr(original, "n_frames", 1) != 1
                ):
                    raise HTTPException(422, "UNSUPPORTED_IMAGE_DIMENSIONS_OR_ANIMATION")
                original.load()
                source = ImageOps.exif_transpose(original).convert("RGBA")
                source.thumbnail((1600, 1600))
                clean = Image.new("RGB", source.size, "white")
                clean.paste(source, mask=source.getchannel("A"))
                output = io.BytesIO()
                clean.save(output, "JPEG", quality=85, optimize=True)
                data = output.getvalue()
                if len(data) > MAX_UPLOAD:
                    raise HTTPException(413, "NORMALIZED_IMAGE_TOO_LARGE")
                return data, clean.width, clean.height
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(422, "INVALID_IMAGE") from None


def media_path(settings, media_id):
    # UUID validation makes traversal impossible; never read a client filename or URL.
    key = str(UUID(str(media_id))) + ".jpg"
    return Path(settings.media_root).resolve() / key


def active_media(session, tenant_id, media_id, purpose=None):
    query = select(MediaObject).where(
        MediaObject.tenant_id == tenant_id,
        MediaObject.id == media_id,
        MediaObject.status == "ACTIVE",
    )
    if purpose:
        query = query.where(MediaObject.purpose == purpose)
    row = session.scalar(query)
    if row is None:
        raise HTTPException(404, "MEDIA_NOT_FOUND")
    return row


def images_json(session, product, public=False):
    rows = session.scalars(
        select(MediaObject)
        .join(
            ProductMedia,
            (MediaObject.id == ProductMedia.media_id)
            & (MediaObject.tenant_id == ProductMedia.tenant_id),
        )
        .where(
            ProductMedia.tenant_id == product.tenant_id,
            ProductMedia.product_id == product.id,
            MediaObject.status == "ACTIVE",
            MediaObject.purpose == "PRODUCT",
        )
        .order_by(ProductMedia.sort_order)
    )
    return [
        {
            "id": str(row.id),
            "width": row.width,
            "height": row.height,
            "url": f"/api/v1/stores/{product.tenant_id}/products/{product.id}/images/{row.id}"
            if public
            else f"/api/v1/merchant/tenants/{product.tenant_id}/media/{row.id}/content",
        }
        for row in rows
    ]
