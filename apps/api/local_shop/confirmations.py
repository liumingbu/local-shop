"""Versioned proposals before preparation; merchant explicitly records customer agreement."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy.orm import Session

from .cancellation_data import pending_cancellation
from .catalog import find_owned
from .models import ConfirmationRevision, RecordEvent, Reservation
from .records import FreeItem, StrictModel, idempotent, reservation_json, snapshot_items


class ConfirmationProposal(StrictModel):
    expected_version: int = Field(ge=1)
    summary: str = Field(default="", max_length=4000)
    items: list[FreeItem] = Field(default_factory=list, max_length=100)
    fulfillment_at: AwareDatetime | None = None
    time_note: str = Field(default="", max_length=200)
    change_reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def content_required(self):
        if not self.summary and not self.items:
            raise ValueError("Confirmation summary or items required")
        return self


def build_router(access):
    router = APIRouter(prefix="/api/v1/merchant")
    database, actor, authorize, key_value = (
        access.database,
        access.actor,
        access.authorize,
        access.key_value,
    )

    @router.post(
        "/tenants/{tenant_id}/reservations/{record_id}/confirmation-revisions", status_code=201
    )
    def propose(
        tenant_id: UUID,
        record_id: UUID,
        payload: ConfirmationProposal,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            row = find_owned(session, Reservation, tenant_id, record_id, lock=True)
            if row.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            if row.status not in {"PENDING_CONFIRMATION", "CONFIRMED"}:
                raise HTTPException(409, "CONFIRMATION_CHANGE_NOT_ALLOWED")
            if pending_cancellation(session, row):
                raise HTTPException(409, "CANCELLATION_REVIEW_REQUIRED")
            details = payload.model_dump(mode="json", exclude={"expected_version"})
            details["items"] = snapshot_items(session, tenant_id, details["items"])
            previous = row.status
            row.status = "PENDING_CONFIRMATION"
            row.version += 1
            row.updated_at = datetime.now(UTC)
            session.add(
                ConfirmationRevision(
                    tenant_id=tenant_id,
                    reservation_id=row.id,
                    actor_id=uid,
                    proposed_version=row.version,
                    details=details,
                )
            )
            session.add(
                RecordEvent(
                    tenant_id=tenant_id,
                    reservation_id=row.id,
                    actor_id=uid,
                    version=row.version,
                    from_status=previous,
                    to_status=row.status,
                    action="CONFIRMATION_PROPOSED",
                    visible_to_customer=True,
                )
            )
            session.flush()
            return reservation_json(row, session)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"confirmation:{record_id}",
            key,
            payload.model_dump(mode="json"),
            action,
        )

    return router
