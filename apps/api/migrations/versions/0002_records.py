"""Owner-entered records and composite tenant event constraints."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002_records"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stores",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "reservations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("customer_label", sa.String(100), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("items", JSONB(), nullable=False),
        sa.Column("fulfillment_method", sa.String(20), nullable=False),
        sa.Column("expected_time_note", sa.String(200), nullable=False),
        sa.Column("internal_note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_reservation_tenant_id"),
        sa.CheckConstraint("version >= 1", name="ck_reservation_version"),
        sa.CheckConstraint(
            "source IN ('MERCHANT_PHONE','MERCHANT_WECHAT','MERCHANT_IN_STORE')",
            name="ck_reservation_source",
        ),
        sa.CheckConstraint(
            "fulfillment_method IN ('PICKUP','DELIVERY')", name="ck_reservation_method"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_CONFIRMATION','CONFIRMED','PREPARING','READY',"
            "'OUT_FOR_DELIVERY','COMPLETED','CANCELLED')",
            name="ck_reservation_status",
        ),
    )
    op.create_index(
        "ix_reservation_tenant_status_created",
        "reservations",
        ["tenant_id", "status", "created_at"],
    )
    op.create_table(
        "record_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("visible_to_customer", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_event_same_tenant",
        ),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("endpoint", sa.String(160), primary_key=True),
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("response", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("idempotency_keys")
    op.drop_table("record_events")
    op.drop_index("ix_reservation_tenant_status_created", table_name="reservations")
    op.drop_table("reservations")
    op.drop_table("stores")
