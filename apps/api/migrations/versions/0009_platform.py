"""Explicit invitations, isolated platform role, versioned tenant status and audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0009_platform"
down_revision = "0008_confirmations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_tenant_version", "tenants", "version >= 1")
    op.create_table(
        "platform_admins",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_platform_admin_status"),
    )
    op.create_table(
        "shop_invitations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("proposed_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('INVITED','ACCEPTED','DECLINED','APPROVED','REJECTED')",
            name="ck_invitation_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_invitation_version"),
        sa.CheckConstraint(
            "(status = 'APPROVED' AND tenant_id IS NOT NULL) OR "
            "(status <> 'APPROVED' AND tenant_id IS NULL)",
            name="ck_invitation_tenant",
        ),
    )
    op.create_index(
        "ix_invitation_owner_status", "shop_invitations", ["owner_user_id", "status", "created_at"]
    )
    op.create_table(
        "platform_operations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("response", JSONB, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id")),
        sa.Column("invitation_id", UUID(as_uuid=True), sa.ForeignKey("shop_invitations.id")),
        sa.Column("before_status", sa.String(20)),
        sa.Column("after_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("actor_id", "key", name="uq_platform_operation_actor_key"),
    )
    op.create_index("ix_platform_operation_time", "platform_operations", ["created_at", "id"])


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM platform_operations) OR "
            "EXISTS(SELECT 1 FROM shop_invitations)"
        )
    ):
        raise RuntimeError(
            "Platform history exists; use reviewed backup recovery, not destructive downgrade"
        )
    op.drop_table("platform_operations")
    op.drop_table("shop_invitations")
    op.drop_table("platform_admins")
    op.drop_constraint("ck_tenant_version", "tenants", type_="check")
    op.drop_column("tenants", "version")
