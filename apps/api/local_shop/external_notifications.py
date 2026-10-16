"""No configured network provider, scheduler or HTTP dispatch endpoint.
Prepare metadata transactionally; explicit dispatcher only sees committed attempts.
Acceptance is never reported as delivery/read; unknown results never automatically retry.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .communication_models import NotificationAttempt
from .notices import envelope
from .records import lock_scope

ResultStatus = Literal["UNCONFIGURED", "REJECTED", "TIMEOUT", "FAILED", "ACCEPTED", "UNKNOWN"]


@dataclass(frozen=True)
class ProviderResult:
    status: ResultStatus


class Provider(Protocol):
    def send(self, notice: dict, deduplication_key: str) -> ProviderResult: ...


def prepare(session, tenant, recipient, audience, event_key):
    envelope(session, tenant, recipient, audience, event_key)
    lock_scope(session, f"notice:{tenant}:{recipient}:{audience}:{event_key}")
    row = session.scalar(
        select(NotificationAttempt).where(
            NotificationAttempt.tenant_id == tenant,
            NotificationAttempt.recipient_id == recipient,
            NotificationAttempt.audience == audience,
            NotificationAttempt.event_key == event_key,
            NotificationAttempt.channel == "UNCONFIGURED",
        )
    )
    if row is None:
        row = NotificationAttempt(
            tenant_id=tenant,
            recipient_id=recipient,
            audience=audience,
            event_key=event_key,
            channel="UNCONFIGURED",
        )
        session.add(row)
        session.flush()
    return row.id


def outcome(row):
    return {
        "id": str(row.id),
        "status": row.status,
        "request_accepted": row.status == "ACCEPTED",
        "delivered": False,
        "read": False,
        "automatic_retry": False,
        "outcome_unknown": row.status in {"UNKNOWN", "TIMEOUT", "IN_PROGRESS"},
    }


def dispatch_once(engine, attempt_id: UUID, provider: Provider | None = None):
    # Reserved internal boundary; production has no provider and no scheduled caller.
    with Session(engine) as session, session.begin():
        row = session.scalar(
            select(NotificationAttempt)
            .where(NotificationAttempt.id == attempt_id)
            .with_for_update()
        )
        if row is None:
            raise HTTPException(404, "ATTEMPT_NOT_FOUND")
        if row.status == "IN_PROGRESS":
            # A concurrent caller must not overwrite a live dispatch result.
            # Stuck IN_PROGRESS is flagged for reconciliation, never auto-resent.
            return outcome(row)
        if row.status != "PENDING":
            return outcome(row)
        try:
            notice = envelope(session, row.tenant_id, row.recipient_id, row.audience, row.event_key)
        except HTTPException:
            row.status = "REJECTED"
            row.result_code = "RECIPIENT_OR_EVENT_UNAVAILABLE"
            return outcome(row)
        row.attempted_at = datetime.now(UTC)
        if provider is None:
            row.status = "UNCONFIGURED"
            row.result_code = "NO_REGISTERED_PROVIDER"
            return outcome(row)
        row.status = "IN_PROGRESS"
        key = str(row.id)
    # Commit claim before the adapter call. Interrupted attempts never auto-resend.
    try:
        result = provider.send(notice, key)
        status = (
            result.status
            if result.status
            in {"UNCONFIGURED", "REJECTED", "TIMEOUT", "FAILED", "ACCEPTED", "UNKNOWN"}
            else "UNKNOWN"
        )
    except TimeoutError:
        status = "TIMEOUT"
    except Exception:
        status = "UNKNOWN"  # raw provider exceptions may contain secrets: discard.
    with Session(engine) as session, session.begin():
        row = session.scalar(
            select(NotificationAttempt)
            .where(NotificationAttempt.id == attempt_id)
            .with_for_update()
        )
        if row.status == "IN_PROGRESS":
            row.status = status
            row.result_code = "ADAPTER_" + status
            if status == "ACCEPTED":
                row.accepted_at = datetime.now(UTC)
        return outcome(row)
