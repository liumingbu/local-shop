import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .attachments import attachments_json, link_private
from .cancellation_data import cancellation_json, pending_cancellation
from .confirmation_data import acknowledge_latest, confirmation_json
from .image_store import active_media
from .models import (
    CancellationRequest,
    Category,
    IdempotencyKey,
    Product,
    RecordEvent,
    Reservation,
    Store,
    Tenant,
    TenantMember,
)

Status = Literal[
    "PENDING_CONFIRMATION",
    "CONFIRMED",
    "PREPARING",
    "READY",
    "OUT_FOR_DELIVERY",
    "COMPLETED",
    "CANCELLED",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FreeItem(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(min_length=1, max_length=20)
    spec: str = Field(default="", max_length=120)
    product_id: UUID | None = None


class NewReservation(StrictModel):
    source: Literal["MERCHANT_PHONE", "MERCHANT_WECHAT", "MERCHANT_IN_STORE"] = "MERCHANT_PHONE"
    customer_label: str = Field(min_length=1, max_length=100)
    raw_text: str = Field(min_length=1, max_length=4000)
    items: list[FreeItem] = Field(default_factory=list, max_length=100)
    fulfillment_method: Literal["PICKUP", "DELIVERY"] = "PICKUP"
    expected_time_note: str = Field(default="", max_length=200)
    internal_note: str = Field(default="", max_length=2000)
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)
    mark_confirmed: bool = False
    expected_at: AwareDatetime | None = None


class Transition(StrictModel):
    confirmation_revision_id: UUID | None = None
    customer_agreed: bool = False
    target_status: Status
    expected_version: int = Field(ge=1)
    note: str = Field(default="", max_length=500)
    visible_to_customer: bool = False


class StoreInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=0)
    published: bool = False
    public_contact: str = Field(default="", max_length=200)
    public_address: str = Field(default="", max_length=300)
    business_hours: str = Field(default="", max_length=200)
    delivery_note: str = Field(default="", max_length=500)
    allow_pickup: bool = False
    allow_delivery: bool = False
    logo_media_id: UUID | None = None


def store_json(row):
    return {"tenant_id": str(row.tenant_id), "version": row.version} | {
        key: getattr(row, key) for key in StoreInput.model_fields if key != "expected_version"
    }


def lock_scope(session, scope: str):
    value = int.from_bytes(
        hashlib.sha256(scope.encode()).digest()[:8], byteorder="big", signed=True
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:value)"), {"value": value})


def reservation_json(record, session=None):
    value = {key: str(getattr(record, key)) for key in ("id", "tenant_id", "actor_id")} | {
        "source": record.source,
        "customer_user_id": str(record.customer_user_id) if record.customer_user_id else None,
        "source_inquiry_id": str(record.source_inquiry_id) if record.source_inquiry_id else None,
        "expected_at": record.expected_at.isoformat() if record.expected_at else None,
        "customer_label": record.customer_label,
        "raw_text": record.raw_text,
        "confirmed_text": record.confirmed_text,
        "items": record.items,
        "fulfillment_method": record.fulfillment_method,
        "expected_time_note": record.expected_time_note,
        "internal_note": record.internal_note,
        "status": record.status,
        "version": record.version,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    if session is not None:
        value["attachments"] = attachments_json(session, record.tenant_id, reservation_id=record.id)
        value["cancellation_requests"] = cancellation_json(session, record)
        value["confirmation_revisions"] = confirmation_json(session, record)
    return value


def idempotent(session, tenant, actor, endpoint, key, payload, action):
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    lock_scope(session, f"{tenant}:{actor}:{endpoint}:{key}")
    existing = session.get(IdempotencyKey, (tenant, actor, endpoint, key))
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
        return existing.response
    response = action()
    session.add(
        IdempotencyKey(
            tenant_id=tenant,
            actor_id=actor,
            endpoint=endpoint,
            key=key,
            payload_hash=digest,
            response=response,
        )
    )
    session.flush()
    return response


def snapshot_items(session, tenant_id, items):
    snapshots = []
    for item in items:
        snapshot = dict(item)
        if item["product_id"]:
            product = session.scalar(
                select(Product)
                .join(
                    Category,
                    (Product.category_id == Category.id)
                    & (Product.tenant_id == Category.tenant_id),
                )
                .where(
                    Product.id == UUID(item["product_id"]),
                    Product.tenant_id == tenant_id,
                    Product.status == "PUBLISHED",
                    Category.status == "ACTIVE",
                )
            )
            if product is None:
                raise HTTPException(404, "PRODUCT_NOT_FOUND")
            snapshot |= {
                "name": product.name,
                "unit": product.unit,
                "spec": product.spec,
                "reference_price": str(product.reference_price)
                if product.reference_price is not None
                else None,
            }
        snapshots.append(snapshot)
    return snapshots


def create_reservation(
    session,
    tenant_id,
    uid,
    data,
    customer_user_id=None,
    source_inquiry_id=None,
    privacy_version=None,
):
    data = dict(data)
    if data.get("expected_at") is not None and isinstance(data["expected_at"], str):
        data["expected_at"] = datetime.fromisoformat(data["expected_at"])
    snapshots = snapshot_items(session, tenant_id, data["items"])
    record = Reservation(
        tenant_id=tenant_id,
        actor_id=uid,
        customer_user_id=customer_user_id,
        source_inquiry_id=source_inquiry_id,
        privacy_version=privacy_version,
        **{k: v for k, v in data.items() if k not in {"mark_confirmed", "items", "media_ids"}},
        items=snapshots,
    )
    record.status = "CONFIRMED" if data.get("mark_confirmed", False) else "PENDING_CONFIRMATION"
    record.version = 2 if data.get("mark_confirmed", False) else 1
    session.add(record)
    session.flush()
    session.add(
        RecordEvent(
            tenant_id=tenant_id,
            reservation_id=record.id,
            actor_id=uid,
            version=1,
            from_status=None,
            to_status="PENDING_CONFIRMATION",
        )
    )
    if data.get("mark_confirmed", False):
        session.add(
            RecordEvent(
                tenant_id=tenant_id,
                reservation_id=record.id,
                actor_id=uid,
                version=2,
                from_status="PENDING_CONFIRMATION",
                to_status="CONFIRMED",
            )
        )
    session.flush()
    link_private(
        session,
        tenant_id,
        uid,
        data.get("media_ids", []),
        reservation_id=record.id,
        visible=customer_user_id == uid,
    )
    return reservation_json(record, session)


def build_router(access):
    router = APIRouter(prefix="/api/v1/merchant")

    database, actor, authorize, key_value = (
        access.database,
        access.actor,
        access.authorize,
        access.key_value,
    )

    @router.get("/tenants")
    def tenants(uid: UUID = Depends(actor), session: Session = Depends(database, scope="function")):
        rows = session.execute(
            select(Tenant, TenantMember)
            .join(TenantMember)
            .where(
                TenantMember.user_id == uid,
                TenantMember.status == "ACTIVE",
                Tenant.status == "ACTIVE",
            )
        )
        return {
            "items": [{"id": str(t.id), "name": t.display_name, "role": m.role} for t, m in rows]
        }

    @router.put("/tenants/{tenant_id}/store")
    def save_store(
        tenant_id: UUID,
        payload: StoreInput,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        membership = authorize(session, tenant_id, uid)
        if membership.role != "OWNER":
            raise HTTPException(403, "OWNER_REQUIRED")
        if payload.logo_media_id is not None:
            active_media(session, tenant_id, payload.logo_media_id, "LOGO")
        lock_scope(session, f"store:{tenant_id}")
        row = session.get(Store, tenant_id)
        current_version = row.version if row else 0
        if payload.expected_version != current_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        if row is None:
            row = Store(
                tenant_id=tenant_id, **payload.model_dump(exclude={"expected_version"}), version=1
            )
            session.add(row)
        else:
            for field, value in payload.model_dump(
                exclude={"expected_version"}, exclude_unset=True
            ).items():
                setattr(row, field, value)
            row.version += 1
        session.flush()
        return store_json(row)

    @router.get("/tenants/{tenant_id}/store")
    def get_store(
        tenant_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        row = session.get(Store, tenant_id)
        if not row:
            raise HTTPException(404, "STORE_NOT_FOUND")
        return store_json(row)

    @router.post("/tenants/{tenant_id}/reservations", status_code=201)
    def create_record(
        tenant_id: UUID,
        payload: NewReservation,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        data = payload.model_dump(mode="json")

        def action():
            return create_reservation(session, tenant_id, uid, data)

        return idempotent(session, tenant_id, uid, "create-reservation", key, data, action)

    @router.get("/tenants/{tenant_id}/reservations")
    def list_records(
        tenant_id: UUID,
        status: Status | None = None,
        cancellation_pending: bool | None = None,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        condition = [Reservation.tenant_id == tenant_id]
        if status:
            condition.append(Reservation.status == status)
        if cancellation_pending is not None:
            pending = select(CancellationRequest.id).where(
                CancellationRequest.tenant_id == Reservation.tenant_id,
                CancellationRequest.reservation_id == Reservation.id,
                CancellationRequest.status == "REQUESTED",
            ).exists()
            condition.append(pending if cancellation_pending else ~pending)
        count = session.scalar(select(func.count()).select_from(Reservation).where(*condition))
        rows = session.scalars(
            select(Reservation)
            .where(*condition)
            .order_by(Reservation.created_at.desc(), Reservation.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return {
            "items": [reservation_json(row, session) for row in rows],
            "total": count,
            "page": page,
            "limit": limit,
        }

    @router.get("/tenants/{tenant_id}/reservations/{record_id}")
    def get_record(
        tenant_id: UUID,
        record_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        record = session.scalar(
            select(Reservation).where(
                Reservation.tenant_id == tenant_id, Reservation.id == record_id
            )
        )
        if record is None:
            raise HTTPException(404, "RECORD_NOT_FOUND")
        events = session.scalars(
            select(RecordEvent)
            .where(RecordEvent.tenant_id == tenant_id, RecordEvent.reservation_id == record_id)
            .order_by(RecordEvent.version)
        )
        return reservation_json(record, session) | {
            "events": [
                {
                    "action": e.action,
                    "from_status": e.from_status,
                    "to_status": e.to_status,
                    "actor_id": str(e.actor_id),
                    "note": e.note,
                    "visible_to_customer": e.visible_to_customer,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ]
        }

    @router.post("/tenants/{tenant_id}/reservations/{record_id}/transitions")
    def transition(
        tenant_id: UUID,
        record_id: UUID,
        payload: Transition,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            row = session.scalar(
                select(Reservation)
                .where(Reservation.tenant_id == tenant_id, Reservation.id == record_id)
                .with_for_update()
            )
            if row is None:
                raise HTTPException(404, "RECORD_NOT_FOUND")
            if row.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            if pending_cancellation(session, row):
                raise HTTPException(409, "CANCELLATION_REVIEW_REQUIRED")
            allowed = {
                "PENDING_CONFIRMATION": {"CONFIRMED", "CANCELLED"},
                "CONFIRMED": {"PREPARING", "CANCELLED"},
                "PREPARING": {"READY", "CANCELLED"},
                "READY": {"COMPLETED", "CANCELLED"}
                if row.fulfillment_method == "PICKUP"
                else {"OUT_FOR_DELIVERY", "CANCELLED"},
                "OUT_FOR_DELIVERY": {"COMPLETED", "CANCELLED"},
                "COMPLETED": set(),
                "CANCELLED": set(),
            }
            if payload.target_status not in allowed[row.status]:
                raise HTTPException(409, "INVALID_TRANSITION")
            if payload.target_status == "CONFIRMED":
                acknowledge_latest(session, row, uid, payload.confirmation_revision_id,
                                   payload.customer_agreed)
            elif payload.confirmation_revision_id or payload.customer_agreed:
                raise HTTPException(422, "CONFIRMATION_FIELDS_NOT_APPLICABLE")
            previous = row.status
            row.status = payload.target_status
            row.version += 1
            row.updated_at = datetime.now(UTC)
            session.add(
                RecordEvent(
                    tenant_id=tenant_id,
                    reservation_id=row.id,
                    actor_id=uid,
                    version=row.version,
                    from_status=previous,
                    to_status=row.status,
                    note=payload.note,
                    visible_to_customer=payload.visible_to_customer,
                )
            )
            session.flush()
            return reservation_json(row, session)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"transition:{record_id}",
            key,
            payload.model_dump(mode="json"),
            action,
        )

    return router
