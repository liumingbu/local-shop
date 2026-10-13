"""Confirmation history is append-only; original request fields are never rewritten."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from .models import ConfirmationRevision


def revisions(session, row):
    return select(ConfirmationRevision).where(
        ConfirmationRevision.tenant_id == row.tenant_id,
        ConfirmationRevision.reservation_id == row.id,
    )


def confirmation_json(session, row):
    return [
        {
            "id": str(revision.id),
            "proposed_version": revision.proposed_version,
            "details": revision.details,
            "created_at": revision.created_at.isoformat(),
            "confirmed_version": revision.confirmed_version,
            "confirmed_at": revision.confirmed_at.isoformat() if revision.confirmed_at else None,
            "agreement_recorded_by": "MERCHANT" if revision.confirmed_at else None,
        }
        for revision in session.scalars(
            revisions(session, row).order_by(ConfirmationRevision.proposed_version)
        )
    ]


def acknowledge_latest(session, row, uid, revision_id, customer_agreed):
    latest = session.scalar(
        revisions(session, row).order_by(ConfirmationRevision.proposed_version.desc()).limit(1)
    )
    if latest is None:
        if revision_id is not None:
            raise HTTPException(409, "CONFIRMATION_REVISION_MISMATCH")
        return
    if latest.id != revision_id or not customer_agreed:
        raise HTTPException(409, "EXPLICIT_RECONFIRMATION_REQUIRED")
    if latest.confirmed_version is not None:
        raise HTTPException(409, "CONFIRMATION_ALREADY_ACKNOWLEDGED")
    latest.confirmed_version = row.version + 1
    latest.confirmed_by = uid
    latest.confirmed_at = datetime.now(UTC)
