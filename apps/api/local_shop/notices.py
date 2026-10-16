"""Unread derives from existing committed business events, not duplicated business state."""

import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import String, and_, case, cast, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .communication_models import NoticeRead
from .models import Inquiry, InquiryEvent, RecordEvent, Reservation, Tenant, TenantMember, User
from .records import StrictModel

Audience = Literal["MERCHANT", "CUSTOMER"]


def require_audience(session, uid, tenant, audience):
    user = session.get(User, uid)
    if not user or user.status != "ACTIVE":
        raise HTTPException(401, "INVALID_IDENTITY")
    if audience == "MERCHANT":
        member = session.scalar(
            select(TenantMember)
            .join(Tenant)
            .where(
                TenantMember.tenant_id == tenant,
                TenantMember.user_id == uid,
                TenantMember.status == "ACTIVE",
                TenantMember.role.in_(["OWNER", "STAFF"]),
                Tenant.status == "ACTIVE",
            )
        )
        if member is None:
            raise HTTPException(404, "TENANT_NOT_FOUND")
    elif audience != "CUSTOMER":
        raise HTTPException(422, "INVALID_AUDIENCE")


def visible_events(tenant, uid, audience):
    reservation = (
        select(
            (literal("r:") + cast(RecordEvent.id, String)).label("event_key"),
            RecordEvent.created_at.label("created_at"),
            literal("reservation").label("kind"),
            RecordEvent.reservation_id.label("record_id"),
            RecordEvent.to_status.label("event_status"),
            RecordEvent.action.label("action"),
            case(
                (RecordEvent.from_status.is_(None), "新需求"),
                (RecordEvent.action == "CANCELLATION_REQUESTED", "收到取消意向"),
                else_="需求状态/确认结果有更新",
            ).label("title"),
        )
        .join(
            Reservation,
            and_(
                Reservation.id == RecordEvent.reservation_id,
                Reservation.tenant_id == RecordEvent.tenant_id,
            ),
        )
        .where(RecordEvent.tenant_id == tenant, RecordEvent.actor_id != uid)
    )
    inquiry = (
        select(
            (literal("i:") + cast(InquiryEvent.id, String)).label("event_key"),
            InquiryEvent.created_at.label("created_at"),
            literal("inquiry").label("kind"),
            InquiryEvent.inquiry_id.label("record_id"),
            InquiryEvent.to_status.label("event_status"),
            InquiryEvent.action.label("action"),
            case(
                (InquiryEvent.action == "CREATED", "新询货更新"),
                else_="询货公开回复/处理结果有更新",
            ).label("title"),
        )
        .join(
            Inquiry,
            and_(
                Inquiry.id == InquiryEvent.inquiry_id, Inquiry.tenant_id == InquiryEvent.tenant_id
            ),
        )
        .where(InquiryEvent.tenant_id == tenant, InquiryEvent.actor_id != uid)
    )
    if audience == "MERCHANT":
        reservation = reservation.where(
            or_(
                RecordEvent.from_status.is_(None),
                RecordEvent.action.in_(["CANCELLATION_REQUESTED", "CONFIRMATION_PROPOSED"]),
            )
        )
        inquiry = inquiry.where(InquiryEvent.action == "CREATED")
    else:
        reservation = reservation.where(
            Reservation.customer_user_id == uid,
            or_(RecordEvent.visible_to_customer.is_(True), RecordEvent.action == "STATUS_CHANGED"),
        )
        inquiry = inquiry.where(
            Inquiry.customer_user_id == uid,
            InquiryEvent.action.in_(["REPLIED", "CLOSED", "CONVERTED"]),
        )
    return union_all(reservation, inquiry).subquery()


def envelope(session, tenant, uid, audience, event_key):
    require_audience(session, uid, tenant, audience)
    source = visible_events(tenant, uid, audience)
    row = session.execute(select(source).where(source.c.event_key == event_key)).mappings().first()
    if row is None:
        raise HTTPException(404, "NOTICE_NOT_FOUND")
    return {
        **dict(row),
        "record_id": str(row["record_id"]),
        "created_at": row["created_at"].isoformat(),
    }


class MarkRead(StrictModel):
    event_keys: list[str] = Field(min_length=1, max_length=100)


def build_router(access):
    router = APIRouter(prefix="/api/v1")
    database, actor = access.database, access.actor

    def listing(tenant, uid, audience, session, page):
        require_audience(session, uid, tenant, audience)
        source = visible_events(tenant, uid, audience)
        join = source.outerjoin(
            NoticeRead,
            and_(
                NoticeRead.tenant_id == tenant,
                NoticeRead.user_id == uid,
                NoticeRead.audience == audience,
                NoticeRead.event_key == source.c.event_key,
            ),
        )
        total, unread = session.execute(
            select(func.count(), func.count().filter(NoticeRead.event_key.is_(None))).select_from(
                join
            )
        ).one()
        values = session.execute(
            select(source, NoticeRead.read_at)
            .select_from(join)
            .order_by(source.c.created_at.desc(), source.c.event_key)
            .offset((page - 1) * 50)
            .limit(50)
        ).mappings()
        return {
            "items": [
                {
                    **dict(r),
                    "record_id": str(r["record_id"]),
                    "created_at": r["created_at"].isoformat(),
                    "read_at": r["read_at"].isoformat() if r["read_at"] else None,
                }
                for r in values
            ],
            "total": total,
            "unread": unread,
            "page": page,
            "limit": 50,
            "audience": audience,
            "as_of": datetime.now(UTC).isoformat(),
            "notice": "未读仅表示此身份尚未查看；不等于待处理，不代表微信已通知。",
        }

    def mark(tenant, uid, audience, session, payload):
        require_audience(session, uid, tenant, audience)
        keys = set(payload.event_keys)
        if any(not re.fullmatch(r"[ri]:[0-9a-f-]{36}", key) for key in keys):
            raise HTTPException(422, "INVALID_NOTICE_KEY")
        source = visible_events(tenant, uid, audience)
        found = set(session.scalars(select(source.c.event_key).where(source.c.event_key.in_(keys))))
        if found != keys:
            raise HTTPException(404, "NOTICE_NOT_FOUND")
        session.execute(
            insert(NoticeRead)
            .values(
                [
                    {"user_id": uid, "tenant_id": tenant, "audience": audience, "event_key": key}
                    for key in keys
                ]
            )
            .on_conflict_do_nothing()
        )
        return {
            "marked": len(keys),
            "business_state_changed": False,
            "external_delivery_claimed": False,
        }

    @router.get("/merchant/tenants/{tenant_id}/updates")
    def merchant(
        tenant_id: UUID,
        page: int = Query(1, ge=1, le=10000),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        access.authorize(session, tenant_id, uid)
        return listing(tenant_id, uid, "MERCHANT", session, page)

    @router.post("/merchant/tenants/{tenant_id}/updates/read")
    def merchant_read(
        tenant_id: UUID,
        payload: MarkRead,
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        access.authorize(session, tenant_id, uid)
        return mark(tenant_id, uid, "MERCHANT", session, payload)

    @router.get("/me/stores/{tenant_id}/updates")
    def customer(
        tenant_id: UUID,
        page: int = Query(1, ge=1, le=10000),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        return listing(tenant_id, uid, "CUSTOMER", session, page)

    @router.post("/me/stores/{tenant_id}/updates/read")
    def customer_read(
        tenant_id: UUID,
        payload: MarkRead,
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        return mark(tenant_id, uid, "CUSTOMER", session, payload)

    @router.get("/notification-capabilities")
    def capabilities(uid=Depends(actor)):
        return {
            "in_app": "AVAILABLE_WHILE_VISIBLE",
            "external_channels": "UNCONFIGURED",
            "automatic_background_delivery": False,
            "accepted_is_delivered": False,
            "delivered_is_read": False,
        }

    return router
