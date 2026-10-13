"""Validated image metadata and ordered same-tenant associations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004_media"
down_revision = "0003_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "media_objects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(100), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(30), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_media_tenant_id"),
        sa.CheckConstraint("purpose IN ('PRODUCT','LOGO')", name="ck_media_purpose"),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_media_status"),
        sa.CheckConstraint("size > 0 AND width > 0 AND height > 0", name="ck_media_dimensions"),
    )
    op.add_column("stores", sa.Column("logo_media_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_store_logo_same_tenant",
        "stores",
        "media_objects",
        ["tenant_id", "logo_media_id"],
        ["tenant_id", "id"],
    )
    op.create_table(
        "product_media",
        sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_image_same_product_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "media_id"],
            ["media_objects.tenant_id", "media_objects.id"],
            name="fk_image_same_media_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "product_id", "sort_order", name="uq_product_image_order"),
    )


def downgrade():
    op.drop_table("product_media")
    op.drop_constraint("fk_store_logo_same_tenant", "stores", type_="foreignkey")
    op.drop_column("stores", "logo_media_id")
    op.drop_table("media_objects")
