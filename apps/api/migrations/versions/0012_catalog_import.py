"""Tenant-scoped bounded CSV previews and durable per-row outcomes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0012_catalog_import"
down_revision = "0011_verified_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_imports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PREVIEW"),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("rows", JSONB(), nullable=False),
        sa.Column("new_categories", JSONB(), nullable=False),
        sa.Column("allow_new_categories", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_duplicates", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('PREVIEW','CONFIRMED')", name="ck_catalog_import_status"),
        sa.CheckConstraint("version >= 1", name="ck_catalog_import_version"),
    )
    op.create_index(
        "ix_catalog_import_tenant_time", "catalog_imports", ["tenant_id", "created_at", "id"]
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM catalog_imports")).scalar():
        raise RuntimeError(
            "Import history requires reviewed restore; refusing destructive downgrade"
        )
    op.drop_table("catalog_imports")
