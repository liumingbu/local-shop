"""Private files with same-tenant record associations and fail-closed public access."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006_private_media"
down_revision = "0005_customers"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("media_objects", sa.Column("privacy_version", sa.String(40), nullable=True))
    op.drop_constraint("ck_media_purpose", "media_objects", type_="check")
    op.create_check_constraint(
        "ck_media_purpose", "media_objects", "purpose IN ('PRODUCT','LOGO','PRIVATE')"
    )
    op.create_table(
        "private_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", UUID(as_uuid=True), nullable=False),
        sa.Column("inquiry_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reservation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("visible_to_customer", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "media_id"],
            ["media_objects.tenant_id", "media_objects.id"],
            name="fk_private_media_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_private_inquiry_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_private_reservation_tenant",
        ),
        sa.CheckConstraint(
            "num_nonnulls(inquiry_id, reservation_id) = 1", name="ck_private_single_parent"
        ),
        sa.UniqueConstraint("tenant_id", "inquiry_id", "media_id", name="uq_private_inquiry_media"),
        sa.UniqueConstraint(
            "tenant_id", "reservation_id", "media_id", name="uq_private_reservation_media"
        ),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM media_objects WHERE purpose='PRIVATE'")):
        raise RuntimeError("Private media exists; restore a verified backup instead of deleting it")
    op.drop_table("private_attachments")
    op.drop_constraint("ck_media_purpose", "media_objects", type_="check")
    op.create_check_constraint("ck_media_purpose", "media_objects", "purpose IN ('PRODUCT','LOGO')")
    op.drop_column("media_objects", "privacy_version")
