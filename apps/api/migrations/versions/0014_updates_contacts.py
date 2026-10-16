"""Existing-event read markers, private contact outcomes and disabled-channel metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0014_updates_contacts"
down_revision = "0013_fulfillment_export"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notice_reads",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("audience", sa.String(20), primary_key=True),
        sa.Column("event_key", sa.String(40), primary_key=True),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("audience IN ('MERCHANT','CUSTOMER')", name="ck_notice_audience"),
    )
    op.create_table(
        "contact_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("inquiry_id", UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_contact_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_contact_inquiry_same_tenant",
        ),
        sa.CheckConstraint(
            "(reservation_id IS NULL) <> (inquiry_id IS NULL)", name="ck_contact_target"
        ),
        sa.CheckConstraint("method IN ('PHONE','WECHAT','NOT_REACHED')", name="ck_contact_method"),
    )
    op.create_index(
        "ix_contact_record", "contact_records", ["tenant_id", "reservation_id", "created_at"]
    )
    op.create_index(
        "ix_contact_inquiry", "contact_records", ["tenant_id", "inquiry_id", "created_at"]
    )
    op.create_table(
        "notification_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("recipient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("event_key", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False, server_default="UNCONFIGURED"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("result_code", sa.String(80), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "recipient_id",
            "audience",
            "event_key",
            "channel",
            name="uq_notification_business_recipient_channel",
        ),
        sa.CheckConstraint("audience IN ('MERCHANT','CUSTOMER')", name="ck_attempt_audience"),
        sa.CheckConstraint(
            "status IN ('PENDING','IN_PROGRESS','UNCONFIGURED','REJECTED',"
            "'TIMEOUT','FAILED','ACCEPTED','UNKNOWN')",
            name="ck_attempt_status",
        ),
        sa.CheckConstraint(
            "delivered_at IS NULL AND read_at IS NULL", name="ck_unverified_delivery_null"
        ),
        sa.CheckConstraint(
            "(status='ACCEPTED' AND accepted_at IS NOT NULL) OR "
            "(status<>'ACCEPTED' AND accepted_at IS NULL)",
            name="ck_attempt_acceptance",
        ),
    )
    op.create_index(
        "ix_record_event_tenant_time", "record_events", ["tenant_id", "created_at", "id"]
    )
    op.create_index(
        "ix_inquiry_event_tenant_time", "inquiry_events", ["tenant_id", "created_at", "id"]
    )


def downgrade():
    connection = op.get_bind()
    if any(
        connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
        for table in ("notice_reads", "contact_records", "notification_attempts")
    ):
        raise RuntimeError(
            "Communication history requires reviewed restore, not destructive downgrade"
        )
    op.drop_index("ix_record_event_tenant_time", table_name="record_events")
    op.drop_index("ix_inquiry_event_tenant_time", table_name="inquiry_events")
    for table in ("notification_attempts", "contact_records", "notice_reads"):
        op.drop_table(table)
