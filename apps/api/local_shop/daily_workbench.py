"""Tenant-scoped daily queue, one-snapshot counters and safe copy-to-draft."""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .catalog import find_owned
from .models import CancellationRequest, Inquiry, Reservation
from .records import FreeItem, snapshot_items

ACTIVE = ("CONFIRMED", "PREPARING", "READY", "OUT_FOR_DELIVERY")


def filters(tenant, day=None, on_date=None, method=None, overdue=False, q=""):
    conditions = [Reservation.tenant_id == tenant]
    if method:
        conditions.append(Reservation.fulfillment_method == method)
    # Queue date uses an explicit merchant promise first, otherwise customer's explicit timestamp.
    # Neither free-text times nor dates without a timestamp become deadlines.
    scheduled = func.coalesce(Reservation.confirmed_due_at, Reservation.expected_at)
    if day == "none":
        conditions.append(scheduled.is_(None))
    elif day:
        target = (
            on_date
            if day == "date"
            else datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=day == "tomorrow")
        )
        if target is None:
            raise HTTPException(422, "DATE_REQUIRED")
        start = datetime.combine(target, time.min, ZoneInfo("Asia/Shanghai"))
        conditions.extend([scheduled >= start, scheduled < start + timedelta(days=1)])
    if overdue:
        conditions.extend(
            [Reservation.confirmed_due_at < datetime.now(UTC), Reservation.status.in_(ACTIVE)]
        )
    if q.strip():
        term = q.strip()
        match = or_(
            Reservation.customer_label.icontains(term, autoescape=True),
            Reservation.raw_text.icontains(term, autoescape=True),
        )
        if (
            term.upper().startswith("LS")
            and term[2:].isascii()
            and term[2:].isdigit()
            and len(term) <= 20
            and int(term[2:]) <= 9223372036854775807
        ):
            match = or_(match, Reservation.business_number == int(term[2:]))
        conditions.append(match)
    return conditions


def build_router(access):
    router = APIRouter(prefix="/api/v1/merchant")
    database, actor, authorize = access.database, access.actor, access.authorize

    @router.get("/tenants/{tenant_id}/workbench-summary")
    def summary(
        tenant_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        counts = [
            func.count().filter(Reservation.status == value).label(value)
            for value in ("PENDING_CONFIRMATION", *ACTIVE, "COMPLETED", "CANCELLED")
        ]
        counts += [
            func.count()
            .filter(
                Reservation.confirmed_due_at < datetime.now(UTC), Reservation.status.in_(ACTIVE)
            )
            .label("OVERDUE")
        ]
        inquiries = (
            select(func.count())
            .select_from(Inquiry)
            .where(Inquiry.tenant_id == tenant_id, Inquiry.status == "NEW")
            .scalar_subquery()
        )
        cancellations = (
            select(func.count())
            .select_from(CancellationRequest)
            .where(
                CancellationRequest.tenant_id == tenant_id,
                CancellationRequest.status == "REQUESTED",
            )
            .scalar_subquery()
        )
        result = (
            session.execute(
                select(
                    *counts,
                    inquiries.label("NEW_INQUIRY"),
                    cancellations.label("CANCELLATION_REQUESTED"),
                ).where(Reservation.tenant_id == tenant_id)
            )
            .mappings()
            .one()
        )
        return {
            "counts": dict(result),
            "as_of": datetime.now(UTC).isoformat(),
            "timezone": "Asia/Shanghai",
        }

    @router.get("/tenants/{tenant_id}/reservations/{record_id}/copy-draft")
    def copy_draft(
        tenant_id: UUID,
        record_id: UUID,
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        row = find_owned(session, Reservation, tenant_id, record_id)
        items, warnings = [], []
        for original in row.items:
            item = FreeItem.model_validate(
                {k: original.get(k) for k in FreeItem.model_fields if k in original}
            ).model_dump(mode="json")
            try:
                current = snapshot_items(session, tenant_id, [item])[0]
                if any(
                    current.get(k) != original.get(k)
                    for k in ("name", "unit", "spec", "reference_price")
                ):
                    warnings.append("商品资料已变化，请重新核对数量、单位、规格与参考价")
                items.append({k: current[k] for k in FreeItem.model_fields if k in current})
            except HTTPException as exc:
                if exc.status_code not in (404, 409):
                    raise
                warnings.append(f"商品暂不可选：{item['name']}；未带入新清单，请重新选货或写明需求")
        return {
            "draft": {
                "customer_label": row.customer_label,
                "raw_text": row.raw_text,
                "items": items,
                "fulfillment_method": row.fulfillment_method,
                "source": "MERCHANT_PHONE",
                "contact_name": row.contact_name,
                "contact_phone": row.contact_phone,
                "delivery_address": row.delivery_address,
                "expected_time_note": "",
                "expected_at": None,
                "internal_note": "",
                "media_ids": [],
                "mark_confirmed": False,
            },
            "warnings": warnings
            + ["这是新需求草稿：须重新核对数量、交付时间和商品；保存后才生成新记录"],
        }

    return router
