"""Verified-owner customer records and distinct inquiries."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0005_customers"
down_revision = "0004_media"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inquiries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "customer_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("product_snapshot", JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("privacy_version", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inquiry_tenant_id"),
        sa.CheckConstraint("status IN ('NEW','REPLIED','CLOSED')", name="ck_inquiry_status"),
    )
    op.create_index(
        "ix_inquiry_tenant_customer_created",
        "inquiries",
        ["tenant_id", "customer_user_id", "created_at"],
    )
    op.create_table(
        "inquiry_replies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("inquiry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("visible_to_customer", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_reply_same_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "inquiry_id", "version", name="uq_reply_version"),
    )
    op.create_table(
        "inquiry_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("inquiry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_inquiry_event_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "inquiry_id", "version", name="uq_inquiry_event_version"),
    )
    op.add_column(
        "reservations", sa.Column("confirmed_text", sa.Text(), nullable=False, server_default="")
    )
    op.add_column("reservations", sa.Column("customer_user_id", UUID(as_uuid=True), nullable=True))
    op.add_column("reservations", sa.Column("source_inquiry_id", UUID(as_uuid=True), nullable=True))
    op.add_column(
        "reservations", sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("reservations", sa.Column("privacy_version", sa.String(40), nullable=True))
    op.create_foreign_key(
        "fk_reservation_customer", "reservations", "users", ["customer_user_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_reservation_inquiry_tenant",
        "reservations",
        "inquiries",
        ["tenant_id", "source_inquiry_id"],
        ["tenant_id", "id"],
    )
    op.create_unique_constraint(
        "uq_inquiry_single_conversion", "reservations", ["tenant_id", "source_inquiry_id"]
    )
    op.create_index(
        "ix_reservation_customer_created",
        "reservations",
        ["customer_user_id", "tenant_id", "created_at"],
    )
    op.drop_constraint("ck_reservation_source", "reservations", type_="check")
    op.create_check_constraint(
        "ck_reservation_source",
        "reservations",
        "source IN ('MERCHANT_PHONE','MERCHANT_WECHAT','MERCHANT_IN_STORE',"
        "'CUSTOMER_MINIAPP','INQUIRY_CONVERSION')",
    )


def downgrade():
    # Refuse destructive conversion of customer-origin records to an owner-origin source.
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT count(*) FROM reservations "
            "WHERE source IN ('CUSTOMER_MINIAPP','INQUIRY_CONVERSION') "
            "OR customer_user_id IS NOT NULL OR source_inquiry_id IS NOT NULL "
            "OR expected_at IS NOT NULL OR confirmed_text <> ''"
        )
    ) or connection.scalar(sa.text("SELECT count(*) FROM inquiries")):
        raise RuntimeError(
            "Customer records exist; restore a verified backup instead of destructive downgrade"
        )
    op.drop_constraint("ck_reservation_source", "reservations", type_="check")
    op.create_check_constraint(
        "ck_reservation_source",
        "reservations",
        "source IN ('MERCHANT_PHONE','MERCHANT_WECHAT','MERCHANT_IN_STORE')",
    )
    op.drop_index("ix_reservation_customer_created", table_name="reservations")
    op.drop_constraint("uq_inquiry_single_conversion", "reservations", type_="unique")
    op.drop_constraint("fk_reservation_inquiry_tenant", "reservations", type_="foreignkey")
    op.drop_constraint("fk_reservation_customer", "reservations", type_="foreignkey")
    for name in (
        "customer_user_id",
        "source_inquiry_id",
        "expected_at",
        "privacy_version",
        "confirmed_text",
    ):
        op.drop_column("reservations", name)
    op.drop_table("inquiry_events")
    op.drop_table("inquiry_replies")
    op.drop_index("ix_inquiry_tenant_customer_created", table_name="inquiries")
    op.drop_table("inquiries")
