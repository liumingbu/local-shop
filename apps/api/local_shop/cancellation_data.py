"""Cancellation DTO deliberately excludes account identifiers and internal notes."""

from sqlalchemy import select

from .list_relations import cached
from .models import CancellationRequest


def pending_cancellation(session, record):
    return session.scalar(
        select(CancellationRequest).where(
            CancellationRequest.tenant_id == record.tenant_id,
            CancellationRequest.reservation_id == record.id,
            CancellationRequest.status == "REQUESTED",
        )
    )


def cancellation_json(session, record):
    rows = cached(session, record.tenant_id, record.id, "cancellations")
    if rows is None:
        rows = session.scalars(
            select(CancellationRequest)
            .where(
                CancellationRequest.tenant_id == record.tenant_id,
                CancellationRequest.reservation_id == record.id,
            )
            .order_by(CancellationRequest.requested_version)
        )
    return [
        {
            "id": str(row.id),
            "reason": row.reason,
            "status": row.status,
            "response_note": row.response_note,
            "requested_version": row.requested_version,
            "decided_version": row.decided_version,
            "created_at": row.created_at.isoformat(),
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        }
        for row in rows
    ]
