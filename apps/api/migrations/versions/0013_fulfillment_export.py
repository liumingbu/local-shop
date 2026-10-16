"""Bounded export audit metadata, without document/PII content."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0013_fulfillment_export"
down_revision = "0012_catalog_import"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fulfillment_exports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("include_contact", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("scope", JSONB(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "actor_id", "key", name="uq_fulfillment_export_key"),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM fulfillment_exports")).scalar():
        raise RuntimeError("Export audit requires reviewed restore, not destructive downgrade")
    op.drop_table("fulfillment_exports")
