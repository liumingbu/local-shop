"""Explicit customer cancellation intent and merchant decision audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007_cancellations"
down_revision = "0006_private_media"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "record_events",
        sa.Column("action", sa.String(40), nullable=False, server_default="STATUS_CHANGED"),
    )
    op.create_table(
        "cancellation_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_note", sa.Text(), nullable=False),
        sa.Column("decision_actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("requested_version", sa.Integer(), nullable=False),
        sa.Column("decided_version", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_cancellation_same_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED','ACCEPTED','REJECTED')", name="ck_cancellation_status"
        ),
        sa.CheckConstraint("requested_version >= 2", name="ck_cancellation_version"),
        sa.CheckConstraint(
            "(status = 'REQUESTED' AND decision_actor_id IS NULL AND decided_at IS NULL "
            "AND decided_version IS NULL) OR (status <> 'REQUESTED' "
            "AND decision_actor_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND decided_version IS NOT NULL "
            "AND decided_version > requested_version)",
            name="ck_cancellation_decision",
        ),
    )
    op.create_index(
        "uq_cancellation_pending",
        "cancellation_requests",
        ["tenant_id", "reservation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'REQUESTED'"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM cancellation_requests")):
        raise RuntimeError("Cancellation history exists; restore a verified backup instead")
    op.drop_table("cancellation_requests")
    op.drop_column("record_events", "action")
