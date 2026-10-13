"""Published stores and same-tenant product catalog."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_catalog"
down_revision = "0002_records"
branch_labels = None
depends_on = None


def upgrade():
    for name, size in (
        ("public_contact", 200),
        ("public_address", 300),
        ("business_hours", 200),
        ("delivery_note", 500),
    ):
        op.add_column("stores", sa.Column(name, sa.String(size), nullable=False, server_default=""))
    for name, value in (
        ("published", "false"),
        ("allow_pickup", "false"),
        ("allow_delivery", "false"),
    ):
        op.add_column(
            "stores", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text(value))
        )
    op.create_table(
        "categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_category_tenant_id"),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_category_status"),
        sa.CheckConstraint("version >= 1", name="ck_category_version"),
    )
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("spec", sa.String(120), nullable=False),
        sa.Column("reference_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("supply_status", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_product_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_product_same_tenant_category",
        ),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_product_status"),
        sa.CheckConstraint(
            "supply_status IN ('REGULAR','CONFIRM','UNAVAILABLE')", name="ck_product_supply"
        ),
        sa.CheckConstraint(
            "reference_price IS NULL OR reference_price >= 0", name="ck_product_price"
        ),
        sa.CheckConstraint("version >= 1", name="ck_product_version"),
    )
    op.create_index("ix_products_tenant_status", "products", ["tenant_id", "status"])


def downgrade():
    op.drop_index("ix_products_tenant_status", table_name="products")
    op.drop_table("products")
    op.drop_table("categories")
    for name in (
        "published",
        "allow_pickup",
        "allow_delivery",
        "public_contact",
        "public_address",
        "business_hours",
        "delivery_note",
    ):
        op.drop_column("stores", name)
