"""Preserve original request and immutable versioned confirmation details."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0008_confirmations"
down_revision = "0007_cancellations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "confirmation_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("proposed_version", sa.Integer(), nullable=False),
        sa.Column("details", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_version", sa.Integer()),
        sa.Column("confirmed_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_confirmation_same_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id", "reservation_id", "proposed_version", name="uq_confirmation_version"
        ),
        sa.CheckConstraint("proposed_version >= 2", name="ck_confirmation_version"),
        sa.CheckConstraint(
            "(confirmed_version IS NULL AND confirmed_by IS NULL AND confirmed_at IS NULL) "
            "OR (confirmed_version IS NOT NULL AND confirmed_by IS NOT NULL "
            "AND confirmed_at IS NOT NULL AND confirmed_version > proposed_version)",
            name="ck_confirmation_ack",
        ),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM confirmation_revisions")):
        raise RuntimeError("Confirmation history exists; restore a verified backup instead")
    op.drop_table("confirmation_revisions")
