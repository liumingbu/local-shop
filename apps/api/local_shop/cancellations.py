"""Customer cancellation intent never directly changes fulfillment state."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cancellation_data import pending_cancellation
from .catalog import find_owned
from .customers import customer_owned, customer_reservation
from .models import CancellationRequest, RecordEvent, Reservation
from .records import StrictModel, idempotent, reservation_json


class CancellationInput(StrictModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class CancellationDecision(StrictModel):
    expected_version: int = Field(ge=1)
    decision: Literal["ACCEPTED", "REJECTED"]
    response_note: str = Field(min_length=1, max_length=500)


def add_event(session, row, uid, before, action):
    session.add(
        RecordEvent(
            tenant_id=row.tenant_id,
            reservation_id=row.id,
            actor_id=uid,
            version=row.version,
            from_status=before,
            to_status=row.status,
            action=action,
            visible_to_customer=True,
        )
    )
    session.flush()


def check_version_and_state(row, expected):
    if row.version != expected:
        raise HTTPException(409, "VERSION_CONFLICT")
    if row.status in {"COMPLETED", "CANCELLED"}:
        raise HTTPException(409, "RECORD_TERMINAL")


def build_router(access):
    router = APIRouter(prefix="/api/v1")
    database, actor, authorize, key_value = (
        access.database,
        access.actor,
        access.authorize,
        access.key_value,
    )

    @router.post("/me/reservations/{record_id}/cancellation-requests", status_code=201)
    def request_cancellation(
        record_id: UUID,
        payload: CancellationInput,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        original = customer_owned(session, Reservation, record_id, uid)
        tenant_id = original.tenant_id

        def action():
            # Reload after the row lock: the initial ownership read may predate another commit.
            row = session.scalar(
                select(Reservation)
                .where(
                    Reservation.id == record_id,
                    Reservation.tenant_id == tenant_id,
                    Reservation.customer_user_id == uid,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None:
                raise HTTPException(404, "RECORD_NOT_FOUND")
            check_version_and_state(row, payload.expected_version)
            if pending_cancellation(session, row):
                raise HTTPException(409, "CANCELLATION_ALREADY_PENDING")
            row.version += 1
            row.updated_at = datetime.now(UTC)
            session.add(
                CancellationRequest(
                    tenant_id=tenant_id,
                    reservation_id=row.id,
                    requester_id=uid,
                    reason=payload.reason,
                    requested_version=row.version,
                )
            )
            add_event(session, row, uid, row.status, "CANCELLATION_REQUESTED")
            return customer_reservation(row, session, detail=True)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"cancel-request:{record_id}",
            key,
            payload.model_dump(mode="json"),
            action,
        )

    @router.post(
        "/merchant/tenants/{tenant_id}/reservations/{record_id}/cancellation-requests/{request_id}/decision"
    )
    def decide_cancellation(
        tenant_id: UUID,
        record_id: UUID,
        request_id: UUID,
        payload: CancellationDecision,
        key: str = Depends(key_value),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        authorize(session, tenant_id, uid)

        def action():
            row = find_owned(session, Reservation, tenant_id, record_id, lock=True)
            check_version_and_state(row, payload.expected_version)
            request = session.scalar(
                select(CancellationRequest).where(
                    CancellationRequest.id == request_id,
                    CancellationRequest.tenant_id == tenant_id,
                    CancellationRequest.reservation_id == record_id,
                )
            )
            if request is None:
                raise HTTPException(404, "CANCELLATION_NOT_FOUND")
            if request.status != "REQUESTED":
                raise HTTPException(409, "CANCELLATION_ALREADY_DECIDED")
            before = row.status
            if payload.decision == "ACCEPTED":
                row.status = "CANCELLED"
            row.version += 1
            row.updated_at = datetime.now(UTC)
            request.status = payload.decision
            request.response_note = payload.response_note
            request.decision_actor_id = uid
            request.decided_at = row.updated_at
            request.decided_version = row.version
            add_event(session, row, uid, before, "CANCELLATION_" + payload.decision)
            return reservation_json(row, session)

        return idempotent(
            session,
            tenant_id,
            uid,
            f"cancel-decision:{request_id}",
            key,
            payload.model_dump(mode="json"),
            action,
        )

    return router
