"""Per-recipient read receipts, private contact notes and disabled-channel attempt metadata."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class NoticeRead(Base):
    __tablename__ = "notice_reads"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    audience: Mapped[str] = mapped_column(String(20), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("audience IN ('MERCHANT','CUSTOMER')", name="ck_notice_audience"),
    )


class ContactRecord(Base):
    __tablename__ = "contact_records"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    inquiry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    method: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_contact_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_contact_inquiry_same_tenant",
        ),
        CheckConstraint(
            "(reservation_id IS NULL) <> (inquiry_id IS NULL)", name="ck_contact_target"
        ),
        CheckConstraint("method IN ('PHONE','WECHAT','NOT_REACHED')", name="ck_contact_method"),
        Index("ix_contact_record", "tenant_id", "reservation_id", "created_at"),
        Index("ix_contact_inquiry", "tenant_id", "inquiry_id", "created_at"),
    )


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    audience: Mapped[str] = mapped_column(String(20))
    event_key: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(30), default="UNCONFIGURED")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    result_code: Mapped[str] = mapped_column(String(80), default="")
    # Never store provider raw errors, payloads, tokens or delivery/read claims.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("audience IN ('MERCHANT','CUSTOMER')", name="ck_attempt_audience"),
        CheckConstraint(
            "status IN ('PENDING','IN_PROGRESS','UNCONFIGURED','REJECTED',"
            "'TIMEOUT','FAILED','ACCEPTED','UNKNOWN')",
            name="ck_attempt_status",
        ),
        CheckConstraint(
            "delivered_at IS NULL AND read_at IS NULL", name="ck_unverified_delivery_null"
        ),
        CheckConstraint(
            "(status='ACCEPTED' AND accepted_at IS NOT NULL) OR "
            "(status<>'ACCEPTED' AND accepted_at IS NULL)",
            name="ck_attempt_acceptance",
        ),
        UniqueConstraint(
            "tenant_id",
            "recipient_id",
            "audience",
            "event_key",
            "channel",
            name="uq_notification_business_recipient_channel",
        ),
    )
