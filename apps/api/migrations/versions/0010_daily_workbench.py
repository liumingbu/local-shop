"""Stable business numbers, contact details and explicit confirmed deadlines."""

import sqlalchemy as sa
from alembic import op

revision = "0010_daily_workbench"
down_revision = "0009_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "reservations", sa.Column("business_number", sa.BigInteger(), sa.Identity(), nullable=False)
    )
    op.create_unique_constraint(
        "uq_reservation_business_number", "reservations", ["business_number"]
    )
    for name, length in [("contact_name", 100), ("contact_phone", 50), ("delivery_address", 500)]:
        op.add_column(
            "reservations", sa.Column(name, sa.String(length), nullable=False, server_default="")
        )
    op.add_column(
        "reservations", sa.Column("confirmed_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Only an acknowledged latest proposal is a promise, never expected_at/text.
    op.execute("""UPDATE reservations r
      SET confirmed_due_at = (c.details->>'fulfillment_at')::timestamptz
      FROM confirmation_revisions c WHERE c.tenant_id=r.tenant_id AND c.reservation_id=r.id
      AND c.confirmed_at IS NOT NULL AND c.details->>'fulfillment_at' IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM confirmation_revisions n WHERE n.tenant_id=c.tenant_id
          AND n.reservation_id=c.reservation_id AND n.proposed_version>c.proposed_version)""")
    op.create_index("ix_reservation_tenant_due", "reservations", ["tenant_id", "confirmed_due_at"])
    op.create_index("ix_reservation_tenant_expected", "reservations", ["tenant_id", "expected_at"])
    op.create_index(
        "ix_reservation_tenant_number", "reservations", ["tenant_id", "business_number"]
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM reservations")).scalar():
        raise RuntimeError("Existing reservation history requires reviewed restore, not downgrade")
    for index in (
        "ix_reservation_tenant_due",
        "ix_reservation_tenant_expected",
        "ix_reservation_tenant_number",
    ):
        op.drop_index(index, table_name="reservations")
    op.drop_constraint("uq_reservation_business_number", "reservations", type_="unique")
    for column in (
        "business_number",
        "contact_name",
        "contact_phone",
        "delivery_address",
        "confirmed_due_at",
    ):
        op.drop_column("reservations", column)
