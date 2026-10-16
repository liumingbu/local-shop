"""Explicit internal contact outcomes; copy/dial actions never create contact records."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .cancellation_data import pending_cancellation
from .catalog import find_owned
from .communication_models import ContactRecord
from .confirmation_data import confirmation_json
from .models import Inquiry, InquiryEvent, RecordEvent, Reservation, Store
from .records import StrictModel, idempotent
from .time_display import business_time


class ContactInput(StrictModel):
    expected_version: int = Field(ge=1)
    method: Literal["PHONE", "WECHAT", "NOT_REACHED"]
    note: str = Field(default="", max_length=500)
    confirmed: bool = False


def contact_json(row):
    return {
        "id": str(row.id),
        "actor_id": str(row.actor_id),
        "method": row.method,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
    }


def build_router(access):
    router = APIRouter(prefix="/api/v1/merchant/tenants/{tenant_id}/{kind}/{record_id}")
    database, actor, authorize = access.database, access.actor, access.authorize

    @router.get("/contacts")
    def listing(
        tenant_id: UUID,
        record_id: UUID,
        kind: Literal["reservations", "inquiries"],
        page: int = Query(1, ge=1, le=10000),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        record = find_owned(
            session, Reservation if kind == "reservations" else Inquiry, tenant_id, record_id
        )
        query = select(ContactRecord).where(
            ContactRecord.tenant_id == tenant_id,
            (ContactRecord.reservation_id if kind == "reservations" else ContactRecord.inquiry_id)
            == record_id,
        )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(ContactRecord.created_at.desc(), ContactRecord.id)
            .offset((page - 1) * 50)
            .limit(50)
        )
        return {
            "items": [contact_json(r) for r in rows],
            "total": total,
            "page": page,
            "limit": 50,
            "record_version": record.version,
            "internal_only": True,
        }

    @router.post("/contacts", status_code=201)
    def add(
        tenant_id: UUID,
        record_id: UUID,
        kind: Literal["reservations", "inquiries"],
        payload: ContactInput,
        key=Depends(access.key_value),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            if not payload.confirmed:
                raise HTTPException(422, "EXPLICIT_CONTACT_OUTCOME_REQUIRED")
            record = find_owned(
                session,
                Reservation if kind == "reservations" else Inquiry,
                tenant_id,
                record_id,
                lock=True,
            )
            if record.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            row = ContactRecord(
                tenant_id=tenant_id,
                **(
                    {"reservation_id": record_id}
                    if kind == "reservations"
                    else {"inquiry_id": record_id}
                ),
                actor_id=uid,
                method=payload.method,
                note=payload.note,
            )
            session.add(row)
            record.version += 1
            if kind == "reservations":
                record.updated_at = datetime.now(UTC)
            if kind == "reservations":
                event = RecordEvent(
                    tenant_id=tenant_id,
                    reservation_id=record_id,
                    actor_id=uid,
                    version=record.version,
                    from_status=record.status,
                    to_status=record.status,
                    action="CONTACT_LOGGED",
                    visible_to_customer=False,
                )
            else:
                event = InquiryEvent(
                    tenant_id=tenant_id,
                    inquiry_id=record_id,
                    actor_id=uid,
                    version=record.version,
                    from_status=record.status,
                    to_status=record.status,
                    action="CONTACT_LOGGED",
                )
            session.add(event)
            session.flush()
            return {
                "contact": contact_json(row),
                "record_version": record.version,
                "business_status": record.status,
                "internal_only": True,
            }

        return idempotent(
            session,
            tenant_id,
            uid,
            f"contact:{kind}:{record_id}",
            key,
            payload.model_dump(),
            action,
        )

    @router.get("/contact-draft")
    def draft(
        tenant_id: UUID,
        record_id: UUID,
        kind: Literal["reservations", "inquiries"],
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        record = find_owned(
            session, Reservation if kind == "reservations" else Inquiry, tenant_id, record_id
        )
        if kind != "reservations":
            raise HTTPException(409, "CONFIRMATION_REQUIRED_FOR_CONTACT_DRAFT")
        revisions = confirmation_json(session, record)
        latest = revisions[-1] if revisions else None
        if record.status == "PENDING_CONFIRMATION" or (
            latest and latest["confirmed_version"] is None
        ):
            raise HTTPException(409, "CONFIRMATION_REQUIRED_FOR_CONTACT_DRAFT")
        store = session.get(Store, tenant_id)
        details = latest["details"] if latest else {"items": record.items}
        names = {
            "CONFIRMED": "已确认",
            "PREPARING": "备货中",
            "READY": "待自提/配送",
            "OUT_FOR_DELIVERY": "配送中",
            "COMPLETED": "已完成",
            "CANCELLED": "已取消",
        }
        lines = [
            f"{store.name if store else '本店'}，需求号LS{record.business_number:010d}。",
            f"当前处理状态：{names[record.status]}。",
        ]
        if pending_cancellation(session, record):
            lines.append("有取消意向待核对，请先联系商家确认最终处理。")
        for item in details.get("items", [])[:20]:
            line = f"{item['name']} {item['spec']}：{item['quantity']}{item['unit']}"
            if len("\n".join(lines)) + len(line) > 3600:
                lines.append("摘要篇幅有限，其余请核对完整需求。")
                break
            lines.append(line)
        if len(details.get("items", [])) > 20:
            lines.append("这里只列前20项摘要，其余请核对完整需求。")
        if record.confirmed_due_at:
            lines.append("商家明确时间：" + business_time(record.confirmed_due_at))
        else:
            lines.append("具体交付时间请进一步确认。")
        return {
            "text": "\n".join(lines),
            "review_required": True,
            "sent": False,
            "logged_contact": False,
            "notice": "仅待核对摘要，不含电话/完整地址/内部备注；复制不表示已发送或联系成功。",
        }

    return router
