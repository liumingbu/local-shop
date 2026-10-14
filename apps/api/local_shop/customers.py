"""Authenticated customer ownership, distinct inquiries and explicit merchant conversion.
All identities remain controlled development identities until real WeChat integration.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .attachments import attachments_json, copy_inquiry_attachments, link_private
from .cancellation_data import cancellation_json
from .catalog import find_owned, published_store
from .confirmation_data import confirmation_json
from .list_relations import prefetch
from .models import (
    Category,
    Inquiry,
    InquiryEvent,
    InquiryReply,
    Product,
    RecordEvent,
    Reservation,
    User,
)
from .records import (
    FreeItem,
    NewReservation,
    StrictModel,
    create_reservation,
    idempotent,
    reservation_json,
)

PRIVACY_VERSION = "development-draft-v1"


class CustomerRequest(StrictModel):
    contact_name: str = Field(default="", max_length=100)
    contact_phone: str = Field(default="", max_length=50)
    delivery_address: str = Field(default="", max_length=500)
    raw_text: str = Field(default="", max_length=4000)
    customer_label: str = Field(default="", max_length=100)
    items: list[FreeItem] = Field(default_factory=list, max_length=100)
    fulfillment_method: Literal["PICKUP", "DELIVERY"] = "PICKUP"
    expected_time_note: str = Field(default="", max_length=200)
    expected_at: AwareDatetime | None = None
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)
    privacy_accepted: Literal[True]

    @model_validator(mode="after")
    def content_required(self):
        if not self.raw_text and not self.items and not self.media_ids:
            raise ValueError("Text or items required")
        return self


class InquiryInput(StrictModel):
    raw_text: str = Field(default="", max_length=4000)
    product_id: UUID | None = None
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)
    privacy_accepted: Literal[True]

    @model_validator(mode="after")
    def content_required(self):
        if not self.raw_text and not self.product_id and not self.media_ids:
            raise ValueError("Inquiry text, product or image required")
        return self


class ReplyInput(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    visible_to_customer: bool = False
    expected_version: int = Field(ge=1)


class InquiryClose(StrictModel):
    expected_version: int = Field(ge=1)


class InquiryConversion(NewReservation):
    expected_version: int = Field(ge=1)


def customer_reservation(row, session, detail=False):
    source = reservation_json(row)
    allowed = (
        "id",
        "tenant_id",
        "business_number",
        "contact_name",
        "contact_phone",
        "delivery_address",
        "confirmed_due_at",
        "source",
        "source_inquiry_id",
        "raw_text",
        "confirmed_text",
        "items",
        "fulfillment_method",
        "expected_time_note",
        "expected_at",
        "status",
        "version",
        "created_at",
        "updated_at",
    )
    value = {name: source[name] for name in allowed}
    value["cancellation_requests"] = cancellation_json(session, row)
    value["confirmation_revisions"] = confirmation_json(session, row)
    value["attachments"] = attachments_json(
        session, row.tenant_id, reservation_id=row.id, customer=True
    )
    if detail:
        events = session.scalars(
            select(RecordEvent)
            .where(RecordEvent.tenant_id == row.tenant_id, RecordEvent.reservation_id == row.id)
            .order_by(RecordEvent.version)
        )
        value["events"] = [
            {
                "action": event.action,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "note": event.note if event.visible_to_customer else "",
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]
    return value


def inquiry_json(row, session, customer=False, detail=False):
    value = {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "raw_text": row.raw_text,
        "product_snapshot": row.product_snapshot,
        "status": row.status,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
    }
    value["attachments"] = attachments_json(
        session, row.tenant_id, inquiry_id=row.id, customer=customer
    )
    converted = session.scalar(
        select(Reservation.id).where(
            Reservation.tenant_id == row.tenant_id, Reservation.source_inquiry_id == row.id
        )
    )
    value["converted_reservation_id"] = str(converted) if converted else None
    if not customer:
        value["customer_user_id"] = str(row.customer_user_id)
    if detail:
        query = select(InquiryReply).where(
            InquiryReply.tenant_id == row.tenant_id, InquiryReply.inquiry_id == row.id
        )
        if customer:
            query = query.where(InquiryReply.visible_to_customer.is_(True))
        value["replies"] = [
            {
                "id": str(reply.id),
                "text": reply.text,
                "visible_to_customer": reply.visible_to_customer,
                "created_at": reply.created_at.isoformat(),
            }
            for reply in session.scalars(query.order_by(InquiryReply.version))
        ]
        events = session.scalars(
            select(InquiryEvent)
            .where(InquiryEvent.tenant_id == row.tenant_id, InquiryEvent.inquiry_id == row.id)
            .order_by(InquiryEvent.version)
        )
        value["events"] = [
            {
                "from_status": event.from_status,
                "to_status": event.to_status,
                "action": event.action,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
            if not customer or event.action != "INTERNAL_NOTE"
        ]
    return value


def record_event(session, row, uid, before, action):
    session.add(
        InquiryEvent(
            tenant_id=row.tenant_id,
            inquiry_id=row.id,
            actor_id=uid,
            from_status=before,
            to_status=row.status,
            action=action,
            version=row.version,
        )
    )
    session.flush()


def customer_owned(session, model, record_id, uid):
    row = session.scalar(select(model).where(model.id == record_id, model.customer_user_id == uid))
    if row is None:
        raise HTTPException(404, "RECORD_NOT_FOUND")
    return row


def build_router(access):
    router = APIRouter(prefix="/api/v1")
    database, actor, authorize, key_value = (
        access.database,
        access.actor,
        access.authorize,
        access.key_value,
    )

    @router.post("/stores/{store_id}/reservations", status_code=201)
    def customer_create(
        store_id: UUID,
        payload: CustomerRequest,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        store = published_store(session, store_id)
        if (payload.fulfillment_method == "PICKUP" and not store.allow_pickup) or (
            payload.fulfillment_method == "DELIVERY" and not store.allow_delivery
        ):
            raise HTTPException(409, "FULFILLMENT_NOT_OFFERED")
        original = payload.model_dump(mode="json")
        data = payload.model_dump(mode="json", exclude={"privacy_accepted"})
        data["customer_label"] = data["customer_label"] or session.get(User, uid).display_name
        data |= {"source": "CUSTOMER_MINIAPP", "mark_confirmed": False, "internal_note": ""}

        def action():
            result = create_reservation(
                session, store_id, uid, data, customer_user_id=uid, privacy_version=PRIVACY_VERSION
            )
            return customer_reservation(
                session.get(Reservation, UUID(result["id"])), session, detail=True
            )

        return idempotent(session, store_id, uid, "customer-reservation", key, original, action)

    @router.post("/stores/{store_id}/inquiries", status_code=201)
    def create_inquiry(
        store_id: UUID,
        payload: InquiryInput,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        published_store(session, store_id)

        def action():
            snapshot = None
            if payload.product_id:
                product = session.scalar(
                    select(Product)
                    .join(
                        Category,
                        (Product.category_id == Category.id)
                        & (Product.tenant_id == Category.tenant_id),
                    )
                    .where(
                        Product.id == payload.product_id,
                        Product.tenant_id == store_id,
                        Product.status == "PUBLISHED",
                        Category.status == "ACTIVE",
                    )
                )
                if product is None:
                    raise HTTPException(404, "PRODUCT_NOT_FOUND")
                snapshot = {
                    "id": str(product.id),
                    "name": product.name,
                    "unit": product.unit,
                    "spec": product.spec,
                    "reference_price": str(product.reference_price)
                    if product.reference_price is not None
                    else None,
                }
            row = Inquiry(
                tenant_id=store_id,
                customer_user_id=uid,
                raw_text=payload.raw_text,
                product_snapshot=snapshot,
                privacy_version=PRIVACY_VERSION,
            )
            session.add(row)
            session.flush()
            link_private(session, store_id, uid, payload.media_ids, inquiry_id=row.id, visible=True)
            record_event(session, row, uid, None, "CREATED")
            return inquiry_json(row, session, customer=True, detail=True)

        return idempotent(
            session, store_id, uid, "customer-inquiry", key, payload.model_dump(mode="json"), action
        )

    @router.get("/me/records")
    def my_records(
        kind: Literal["reservation", "inquiry"] = "reservation",
        store_id: UUID | None = None,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        model = Reservation if kind == "reservation" else Inquiry
        query = select(model).where(model.customer_user_id == uid)
        if store_id:
            query = query.where(model.tenant_id == store_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(model.created_at.desc(), model.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = list(rows)
        if kind == "reservation":
            prefetch(session, rows)
        items = [
            customer_reservation(row, session)
            if kind == "reservation"
            else inquiry_json(row, session, customer=True)
            for row in rows
        ]
        return {"items": items, "total": total, "page": page, "limit": limit}

    @router.get("/me/records/reservation/{record_id}")
    def my_reservation(
        record_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        return customer_reservation(
            customer_owned(session, Reservation, record_id, uid), session, detail=True
        )

    @router.get("/me/records/inquiry/{record_id}")
    def my_inquiry(
        record_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        return inquiry_json(
            customer_owned(session, Inquiry, record_id, uid), session, customer=True, detail=True
        )

    @router.get("/merchant/tenants/{tenant_id}/inquiries")
    def merchant_inquiries(
        tenant_id: UUID,
        status: Literal["NEW", "REPLIED", "CLOSED"] | None = None,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        query = select(Inquiry).where(Inquiry.tenant_id == tenant_id)
        if status:
            query = query.where(Inquiry.status == status)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(Inquiry.created_at.desc(), Inquiry.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return {
            "items": [inquiry_json(row, session) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @router.get("/merchant/tenants/{tenant_id}/inquiries/{inquiry_id}")
    def merchant_inquiry(
        tenant_id: UUID,
        inquiry_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        return inquiry_json(
            find_owned(session, Inquiry, tenant_id, inquiry_id), session, detail=True
        )

    @router.post("/merchant/tenants/{tenant_id}/inquiries/{inquiry_id}/replies", status_code=201)
    def reply(
        tenant_id: UUID,
        inquiry_id: UUID,
        payload: ReplyInput,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            row = find_owned(session, Inquiry, tenant_id, inquiry_id, lock=True)
            if row.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            if row.status == "CLOSED":
                raise HTTPException(409, "INQUIRY_CLOSED")
            before = row.status
            row.version += 1
            if payload.visible_to_customer:
                row.status = "REPLIED"
            session.add(
                InquiryReply(
                    tenant_id=tenant_id,
                    inquiry_id=inquiry_id,
                    actor_id=uid,
                    text=payload.text,
                    visible_to_customer=payload.visible_to_customer,
                    version=row.version,
                )
            )
            record_event(
                session,
                row,
                uid,
                before,
                "REPLIED" if payload.visible_to_customer else "INTERNAL_NOTE",
            )
            return inquiry_json(row, session, detail=True)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"reply:{inquiry_id}",
            key,
            payload.model_dump(mode="json"),
            action,
        )

    @router.post("/merchant/tenants/{tenant_id}/inquiries/{inquiry_id}/close")
    def close(
        tenant_id: UUID,
        inquiry_id: UUID,
        payload: InquiryClose,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            row = find_owned(session, Inquiry, tenant_id, inquiry_id, lock=True)
            if row.version != payload.expected_version or row.status == "CLOSED":
                raise HTTPException(409, "VERSION_OR_STATE_CONFLICT")
            before = row.status
            row.status = "CLOSED"
            row.version += 1
            record_event(session, row, uid, before, "CLOSED")
            return inquiry_json(row, session, detail=True)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"close:{inquiry_id}",
            key,
            payload.model_dump(mode="json"),
            action,
        )

    @router.post("/merchant/tenants/{tenant_id}/inquiries/{inquiry_id}/convert", status_code=201)
    def convert(
        tenant_id: UUID,
        inquiry_id: UUID,
        payload: InquiryConversion,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            row = find_owned(session, Inquiry, tenant_id, inquiry_id, lock=True)
            if row.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            if row.status == "CLOSED":
                raise HTTPException(409, "INQUIRY_CLOSED")
            if session.scalar(
                select(Reservation.id).where(
                    Reservation.tenant_id == tenant_id, Reservation.source_inquiry_id == inquiry_id
                )
            ):
                raise HTTPException(409, "INQUIRY_ALREADY_CONVERTED")
            data = payload.model_dump(mode="json", exclude={"expected_version"})
            # Retain original inquiry text; explicit confirmation details remain item snapshots.
            data["confirmed_text"] = payload.raw_text
            data["raw_text"] = row.raw_text
            data["source"] = "INQUIRY_CONVERSION"
            result = create_reservation(
                session,
                tenant_id,
                uid,
                data,
                customer_user_id=row.customer_user_id,
                source_inquiry_id=row.id,
                privacy_version=row.privacy_version,
            )
            copy_inquiry_attachments(session, tenant_id, row.id, UUID(result["id"]))
            row.version += 1
            record_event(session, row, uid, row.status, "CONVERTED")
            return reservation_json(session.get(Reservation, UUID(result["id"])), session)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"convert:{inquiry_id}",
            key,
            payload.model_dump(mode="json"),
            action,
        )

    return router
