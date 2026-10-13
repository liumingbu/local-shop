import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .identity import DEMO_USERS, read_demo_token, require_local
from .models import IdempotencyKey, RecordEvent, Reservation, Store, Tenant, TenantMember, User

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
    product_id: None = None


class NewReservation(StrictModel):
    source: Literal["MERCHANT_PHONE", "MERCHANT_WECHAT", "MERCHANT_IN_STORE"] = "MERCHANT_PHONE"
    customer_label: str = Field(min_length=1, max_length=100)
    raw_text: str = Field(min_length=1, max_length=4000)
    items: list[FreeItem] = Field(default_factory=list, max_length=100)
    fulfillment_method: Literal["PICKUP", "DELIVERY"] = "PICKUP"
    expected_time_note: str = Field(default="", max_length=200)
    internal_note: str = Field(default="", max_length=2000)
    mark_confirmed: bool = False


class Transition(StrictModel):
    target_status: Status
    expected_version: int = Field(ge=1)
    note: str = Field(default="", max_length=500)
    visible_to_customer: bool = False


class StoreInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=0)


class IdempotencyInput(StrictModel):
    key: str = Field(min_length=8, max_length=100)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value):
        if not value.isascii() or not all(c.isalnum() or c in "-_." for c in value):
            raise ValueError("Invalid idempotency key")
        return value


def lock_scope(session, scope: str):
    value = int.from_bytes(
        hashlib.sha256(scope.encode()).digest()[:8], byteorder="big", signed=True
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:value)"), {"value": value})


def reservation_json(record):
    return {key: str(getattr(record, key)) for key in ("id", "tenant_id", "actor_id")} | {
        "source": record.source,
        "customer_label": record.customer_label,
        "raw_text": record.raw_text,
        "items": record.items,
        "fulfillment_method": record.fulfillment_method,
        "expected_time_note": record.expected_time_note,
        "internal_note": record.internal_note,
        "status": record.status,
        "version": record.version,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


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


def build_router(settings, engine):
    router = APIRouter(prefix="/api/v1/merchant")

    def database():
        with Session(engine) as session, session.begin():
            yield session

    def actor(request: Request, session: Session = Depends(database, scope="function")):
        if not settings.dev_auth_enabled:
            raise HTTPException(401, "AUTHENTICATION_REQUIRED")
        require_local(request)
        bearer = request.headers.get("Authorization", "")
        if not bearer.startswith("Bearer "):
            raise HTTPException(401, "INVALID_TOKEN")
        try:
            claims = read_demo_token(bearer[7:], settings)
            if claims["kind"] != "development" or claims["sub"] not in DEMO_USERS.values():
                raise HTTPException(401, "INVALID_TOKEN")
            uid = UUID(claims["sub"])
        except (jwt.InvalidTokenError, ValueError):
            raise HTTPException(401, "INVALID_TOKEN") from None
        user = session.get(User, uid)
        if user is None or user.status != "ACTIVE" or user.identity_type != "DEVELOPMENT":
            raise HTTPException(401, "INVALID_IDENTITY")
        return uid

    def authorize(session, tenant_id, uid):
        row = session.execute(
            select(TenantMember, Tenant)
            .join(Tenant)
            .where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == uid,
                TenantMember.status == "ACTIVE",
                Tenant.status == "ACTIVE",
                TenantMember.role.in_(["OWNER", "STAFF"]),
            )
        ).first()
        if row is None:
            raise HTTPException(404, "TENANT_NOT_FOUND")
        return row[0]

    def key_value(idempotency_key: str = Header(..., alias="Idempotency-Key")):
        try:
            return IdempotencyInput(key=idempotency_key).key
        except ValueError:
            raise HTTPException(422, "INVALID_IDEMPOTENCY_KEY") from None

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
        lock_scope(session, f"store:{tenant_id}")
        row = session.get(Store, tenant_id)
        current_version = row.version if row else 0
        if payload.expected_version != current_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        if row is None:
            row = Store(
                tenant_id=tenant_id, name=payload.name, description=payload.description, version=1
            )
            session.add(row)
        else:
            row.name = payload.name
            row.description = payload.description
            row.version += 1
        session.flush()
        return {
            "tenant_id": str(tenant_id),
            "name": row.name,
            "description": row.description,
            "version": row.version,
        }

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
        return {
            "tenant_id": str(tenant_id),
            "name": row.name,
            "description": row.description,
            "version": row.version,
        }

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
            record = Reservation(
                tenant_id=tenant_id,
                actor_id=uid,
                **{k: v for k, v in data.items() if k != "mark_confirmed"},
            )
            record.status = "CONFIRMED" if payload.mark_confirmed else "PENDING_CONFIRMATION"
            record.version = 2 if payload.mark_confirmed else 1
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
            if payload.mark_confirmed:
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
            return reservation_json(record)

        return idempotent(session, tenant_id, uid, "create-reservation", key, data, action)

    @router.get("/tenants/{tenant_id}/reservations")
    def list_records(
        tenant_id: UUID,
        status: Status | None = None,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        condition = [Reservation.tenant_id == tenant_id]
        if status:
            condition.append(Reservation.status == status)
        count = session.scalar(select(func.count()).select_from(Reservation).where(*condition))
        rows = session.scalars(
            select(Reservation)
            .where(*condition)
            .order_by(Reservation.created_at.desc(), Reservation.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return {
            "items": [reservation_json(row) for row in rows],
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
        return reservation_json(record) | {
            "events": [
                {
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
            return reservation_json(row)

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
