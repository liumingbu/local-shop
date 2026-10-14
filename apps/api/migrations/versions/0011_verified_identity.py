"""Provider-bound identities, revocable sessions and one-use browser approvals."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0011_verified_identity"
down_revision = "0010_daily_workbench"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("account_code", sa.String(20), nullable=True))
    op.create_unique_constraint("uq_user_account_code", "users", ["account_code"])
    op.create_table(
        "wechat_identities",
        sa.Column("appid", sa.String(32), primary_key=True),
        sa.Column("openid", sa.String(128), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True
        ),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_auth_session_user", "auth_sessions", ["user_id"])
    op.create_table(
        "used_login_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "auth_rate_windows",
        sa.Column("bucket", sa.String(100), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "browser_approvals",
        sa.Column("secret_hash", sa.String(64), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    connection = op.get_bind()
    if any(
        connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
        for table in ("wechat_identities", "auth_sessions", "browser_approvals")
    ):
        raise RuntimeError(
            "Verified identities and sessions require reviewed restore, not downgrade"
        )
    for table in (
        "browser_approvals",
        "auth_rate_windows",
        "used_login_codes",
        "auth_sessions",
        "wechat_identities",
    ):
        op.drop_table(table)
    op.drop_constraint("uq_user_account_code", "users", type_="unique")
    op.drop_column("users", "account_code")
