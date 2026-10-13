"""Private association ownership is independent of public product media."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from .image_store import active_media
from .models import Inquiry, MediaObject, PrivateAttachment, Reservation


def link_private(
    session, tenant_id, uid, media_ids, *, inquiry_id=None, reservation_id=None, visible=False
):
    if len(media_ids) > 5 or len(set(str(mid) for mid in media_ids)) != len(media_ids):
        raise HTTPException(422, "INVALID_ATTACHMENT_LIST")
    for position, value in enumerate(media_ids):
        mid = UUID(str(value))
        media = active_media(session, tenant_id, mid, "PRIVATE")
        if media.owner_id != uid:
            raise HTTPException(404, "MEDIA_NOT_FOUND")
        session.add(
            PrivateAttachment(
                tenant_id=tenant_id,
                media_id=mid,
                inquiry_id=inquiry_id,
                reservation_id=reservation_id,
                visible_to_customer=visible,
                sort_order=position,
            )
        )
    session.flush()


def copy_inquiry_attachments(session, tenant_id, inquiry_id, reservation_id):
    existing = set(
        session.scalars(
            select(PrivateAttachment.media_id).where(
                PrivateAttachment.tenant_id == tenant_id,
                PrivateAttachment.reservation_id == reservation_id,
            )
        )
    )
    rows = session.scalars(
        select(PrivateAttachment)
        .where(PrivateAttachment.tenant_id == tenant_id, PrivateAttachment.inquiry_id == inquiry_id)
        .order_by(PrivateAttachment.sort_order, PrivateAttachment.id)
    )
    rows = list(rows)
    if len(existing | {row.media_id for row in rows}) > 5:
        raise HTTPException(422, "TOO_MANY_ATTACHMENTS")
    next_position = len(existing)
    for row in rows:
        if row.media_id in existing:
            continue
        session.add(
            PrivateAttachment(
                tenant_id=tenant_id,
                media_id=row.media_id,
                reservation_id=reservation_id,
                visible_to_customer=row.visible_to_customer,
                sort_order=next_position,
            )
        )
        next_position += 1
    session.flush()


def attachments_json(session, tenant_id, *, inquiry_id=None, reservation_id=None, customer=False):
    query = select(MediaObject, PrivateAttachment).join(
        PrivateAttachment,
        (MediaObject.id == PrivateAttachment.media_id)
        & (MediaObject.tenant_id == PrivateAttachment.tenant_id),
    )
    query = query.where(
        PrivateAttachment.tenant_id == tenant_id,
        MediaObject.purpose == "PRIVATE",
        MediaObject.status == "ACTIVE",
    )
    if inquiry_id:
        query = query.where(PrivateAttachment.inquiry_id == inquiry_id)
    else:
        query = query.where(PrivateAttachment.reservation_id == reservation_id)
    if customer:
        query = query.where(PrivateAttachment.visible_to_customer.is_(True))
    rows = session.execute(query.order_by(PrivateAttachment.sort_order, PrivateAttachment.id))
    return [
        {
            "id": str(media.id),
            "width": media.width,
            "height": media.height,
            "url": f"/api/v1/me/media/{media.id}/content?store_id={tenant_id}"
            if customer
            else f"/api/v1/merchant/tenants/{tenant_id}/media/{media.id}/content",
        }
        for media, _ in rows
    ]


def require_merchant_private_access(session, media, uid):
    if media.purpose != "PRIVATE" or media.owner_id == uid:
        return
    linked = session.scalar(
        select(PrivateAttachment.id)
        .where(
            PrivateAttachment.tenant_id == media.tenant_id, PrivateAttachment.media_id == media.id
        )
        .limit(1)
    )
    if linked is None:
        # A customer's uploaded but unsubmitted image is not available to the shop.
        raise HTTPException(404, "MEDIA_NOT_FOUND")


def require_customer_private_access(session, media, uid):
    if media.purpose != "PRIVATE":
        raise HTTPException(404, "MEDIA_NOT_FOUND")
    if media.owner_id == uid:
        return
    for model, field in (
        (Reservation, PrivateAttachment.reservation_id),
        (Inquiry, PrivateAttachment.inquiry_id),
    ):
        linked = session.scalar(
            select(PrivateAttachment.id)
            .join(model, (field == model.id) & (PrivateAttachment.tenant_id == model.tenant_id))
            .where(
                PrivateAttachment.tenant_id == media.tenant_id,
                PrivateAttachment.media_id == media.id,
                PrivateAttachment.visible_to_customer.is_(True),
                model.customer_user_id == uid,
            )
            .limit(1)
        )
        if linked:
            return
    raise HTTPException(404, "MEDIA_NOT_FOUND")
