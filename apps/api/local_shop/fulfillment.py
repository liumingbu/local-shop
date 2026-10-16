"""Derived, bounded confirmed pick lists and explicitly scoped private handover documents."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .csv_core import display_csv
from .daily_workbench import filters
from .fulfillment_models import FulfillmentExport
from .list_relations import cached, prefetch
from .models import Reservation
from .records import StrictModel, lock_scope
from .time_display import business_time

PHASES = {
    "PREPARING": ("CONFIRMED", "PREPARING"),
    "DELIVERY": ("READY", "OUT_FOR_DELIVERY"),
    "ACTIVE": ("CONFIRMED", "PREPARING", "READY", "OUT_FOR_DELIVERY"),
}


class Scope(StrictModel):
    day: Literal["today", "tomorrow", "date", "none"] | None = None
    on_date: date | None = None
    method: Literal["PICKUP", "DELIVERY"] | None = None
    phase: Literal["PREPARING", "DELIVERY", "ACTIVE"] = "PREPARING"
    q: str = Field(default="", max_length=200)


class Export(StrictModel):
    scope: Scope = Field(default_factory=Scope)
    expected_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    purpose: Literal["PREPARATION", "HANDOVER"]
    format: Literal["CSV", "TEXT", "PRINT"] = "CSV"
    include_contact: bool = False
    contact_acknowledged: bool = False


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def collect(session, tenant, scope):
    rows = list(
        session.scalars(
            select(Reservation)
            .where(
                *filters(tenant, scope.day, scope.on_date, scope.method, q=scope.q),
                Reservation.status.in_(PHASES[scope.phase]),
            )
            .order_by(Reservation.business_number)
            .limit(201)
            .with_for_update(read=True)
        )
    )
    if len(rows) > 200:
        raise HTTPException(422, "NARROW_FULFILLMENT_RANGE_MAX_200")
    prefetch(session, rows)
    orders = []
    groups = {}
    review = []
    for row in rows:
        revisions = cached(session, row.tenant_id, row.id, "revisions")
        latest = revisions[-1] if revisions else None
        cancellations = cached(session, row.tenant_id, row.id, "cancellations")
        details = (
            latest.details
            if latest
            else {
                "items": row.items,
                "summary": row.confirmed_text,
                "time_note": row.expected_time_note,
            }
        )
        reasons = []
        if latest and latest.confirmed_version is None:
            reasons.append("最新变更尚未明确确认")
        if any(c.status == "REQUESTED" for c in cancellations):
            reasons.append("取消意向待决定")
        items = details.get("items", [])
        if not items or any(not item.get("product_id") for item in items):
            reasons.append("自由文本或手工明细需人工核对，不跨单汇总")
        number = f"LS{row.business_number:010d}"
        order = {
            "id": str(row.id),
            "business_number": number,
            "version": row.version,
            "status": row.status,
            "method": row.fulfillment_method,
            "confirmed_due_at": row.confirmed_due_at.isoformat() if row.confirmed_due_at else None,
            "time_note": details.get("time_note", ""),
            "items": items,
            "review_reasons": reasons,
            "manual_text": row.raw_text if reasons else "",
            "summary": details.get("summary", ""),
        }
        orders.append(order)
        if reasons:
            review.append({"id": str(row.id), "business_number": number, "reasons": reasons})
            continue
        for item in items:
            key = (item["product_id"], item["name"], item["spec"], item["unit"])
            if key not in groups:
                groups[key] = {
                    "product_id": key[0],
                    "name": key[1],
                    "spec": key[2],
                    "unit": key[3],
                    "quantity": Decimal(0),
                    "sources": {},
                }
            groups[key]["quantity"] += Decimal(item["quantity"])
            sources = groups[key]["sources"]
            identifier = str(row.id)
            if identifier in sources:
                sources[identifier]["quantity"] = format(
                    Decimal(sources[identifier]["quantity"]) + Decimal(item["quantity"]), "f"
                )
            else:
                sources[identifier] = {
                    "id": identifier,
                    "business_number": number,
                    "quantity": item["quantity"],
                }
    values = list(groups.values())
    for group in values:
        group["quantity"] = format(group["quantity"], "f")
        group["orders"] = list(group.pop("sources").values())
    digest = fingerprint(
        {"scope": scope.model_dump(mode="json"), "records": [(str(r.id), r.version) for r in rows]}
    )
    return {
        "orders": orders,
        "groups": values,
        "needs_review": review,
        "fingerprint": digest,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": scope.model_dump(mode="json"),
        "count": len(rows),
        "max_records": 200,
        "notice": (
            "仅明确确认且可规范汇总的选中单；需核对单不计入总量。不换算单位，不代表库存或交付完成。"
        ),
    }, rows


def document(snapshot, rows, payload, when):
    lines = [
        ["local-shop", "备货单" if payload.purpose == "PREPARATION" else "配送/自提清单"],
        ["生成时间", business_time(when)],
        [
            "范围",
            json.dumps(
                (
                    {k: v for k, v in snapshot["scope"].items() if k != "q"}
                    | {
                        "has_search": bool(snapshot["scope"]["q"]),
                        "record_count": snapshot["count"],
                    }
                ),
                ensure_ascii=False,
            ),
        ],
        ["注意", "需核对项不计入汇总；本文件非实时，导出/打印不改变业务状态"],
    ]
    if payload.purpose == "PREPARATION":
        lines.append(["商品", "规格", "数量", "单位", "来源业务号"])
        for item in snapshot["groups"]:
            lines.append(
                [
                    item["name"],
                    item["spec"],
                    item["quantity"],
                    item["unit"],
                    " / ".join(o["business_number"] for o in item["orders"]),
                ]
            )
    else:
        lines.append(
            ["业务号", "方式", "明确交付时间", "明细", "需核对"]
            + (["联系人", "联系电话", "配送地址"] if payload.include_contact else [])
        )
        for row, order in zip(rows, snapshot["orders"], strict=True):
            lines.append(
                [
                    order["business_number"],
                    order["method"],
                    business_time(order["confirmed_due_at"]),
                    " / ".join(
                        f"{i['name']} {i['spec']} {i['quantity']}{i['unit']}"
                        for i in order["items"]
                    ),
                    "；".join(order["review_reasons"]),
                ]
                + (
                    [
                        row.contact_name,
                        row.contact_phone,
                        row.delivery_address if row.fulfillment_method == "DELIVERY" else "",
                    ]
                    if payload.include_contact
                    else []
                )
            )
    lines.append(["需人工核对的业务号", "原因（原文请回授权记录查看）"])
    lines.extend(
        [[o["business_number"], "；".join(o["reasons"])] for o in snapshot["needs_review"]]
    )
    if payload.format == "CSV":
        return display_csv(lines)
    return "\n".join(
        " | ".join(str(v).replace("\r", " ").replace("\n", " ") for v in line) for line in lines
    )


def build_router(access):
    router = APIRouter(prefix="/api/v1/merchant/tenants/{tenant_id}")
    database, actor, authorize = access.database, access.actor, access.authorize

    def scope_query(
        day: Literal["today", "tomorrow", "date", "none"] | None = None,
        on_date: date | None = None,
        method: Literal["PICKUP", "DELIVERY"] | None = None,
        phase: Literal["PREPARING", "DELIVERY", "ACTIVE"] = "PREPARING",
        q: str = Query("", max_length=200),
    ):
        return Scope(day=day, on_date=on_date, method=method, phase=phase, q=q)

    @router.get("/fulfillment")
    def listing(
        tenant_id: UUID,
        scope: Scope = Depends(scope_query),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        return collect(session, tenant_id, scope)[0]

    @router.post("/fulfillment/exports")
    def export(
        tenant_id: UUID,
        payload: Export,
        key=Depends(access.key_value),
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)
        if payload.include_contact and (
            payload.purpose != "HANDOVER" or not payload.contact_acknowledged
        ):
            raise HTTPException(422, "CONTACT_EXPORT_REQUIRES_EXPLICIT_HANDOVER_PURPOSE")
        snapshot, rows = collect(session, tenant_id, payload.scope)
        if snapshot["fingerprint"] != payload.expected_fingerprint:
            raise HTTPException(409, "LIST_CHANGED_REFRESH_REQUIRED")
        lock_scope(session, f"export:{tenant_id}:{uid}:{key}")
        digest = fingerprint(payload.model_dump(mode="json"))
        audit = session.scalar(
            select(FulfillmentExport).where(
                FulfillmentExport.tenant_id == tenant_id,
                FulfillmentExport.actor_id == uid,
                FulfillmentExport.key == key,
            )
        )
        if audit and audit.payload_hash != digest:
            raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED")
        if not audit:
            scope = payload.scope.model_dump(mode="json", exclude={"q"}) | {
                "has_search": bool(payload.scope.q),
                "record_ids": [str(r.id) for r in rows],
                "fingerprint": snapshot["fingerprint"],
            }
            audit = FulfillmentExport(
                tenant_id=tenant_id,
                actor_id=uid,
                key=key,
                payload_hash=digest,
                purpose=payload.purpose,
                format=payload.format,
                include_contact=payload.include_contact,
                scope=scope,
                record_count=len(rows),
            )
            session.add(audit)
            session.flush()
        when = audit.created_at.isoformat()
        return {
            "content": document(snapshot, rows, payload, when),
            "format": payload.format,
            "audit_id": str(audit.id),
            "generated_at": when,
            "fingerprint": snapshot["fingerprint"],
            "includes_contact": payload.include_contact,
            "filename": (
                f"local-shop-{payload.purpose.lower()}."
                + ("csv" if payload.format == "CSV" else "txt")
            ),
            "notice": (
                "仅本次授权获取，不提供公开固定链接；不含内部备注。请妥善保管含联系信息的文件。"
            ),
        }

    return router
