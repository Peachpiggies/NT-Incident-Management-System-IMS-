"""Add device metadata and logical session identifiers.

Revision ID: 0003_session_metadata
Revises: 0002_operational_indexes
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_session_metadata"
down_revision = "0002_operational_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial revision creates metadata dynamically, so a fresh database
    # already contains columns added to the current model.  Existing 0002
    # databases need the ALTERs below; both paths must be migration-safe.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]: column for column in inspector.get_columns("refresh_tokens")
    }
    additions = [
        ("session_id", sa.Column("session_id", sa.Uuid(), nullable=True)),
        ("login_history_id", sa.Column("login_history_id", sa.Uuid(), nullable=True)),
        ("ip", sa.Column("ip", sa.String(length=64), nullable=True)),
        ("device", sa.Column("device", sa.String(length=255), nullable=True)),
        ("browser", sa.Column("browser", sa.String(length=255), nullable=True)),
        ("user_agent", sa.Column("user_agent", sa.String(length=500), nullable=True)),
        (
            "last_used_at",
            sa.Column(
                "last_used_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        ),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("refresh_tokens", column)

    inspector = sa.inspect(bind)
    foreign_keys = {
        item["name"] for item in inspector.get_foreign_keys("refresh_tokens")
    }
    foreign_key_name = "fk_refresh_tokens_login_history_id_login_histories"
    if foreign_key_name not in foreign_keys:
        op.create_foreign_key(
            op.f(foreign_key_name),
            "refresh_tokens",
            "login_histories",
            ["login_history_id"],
            ["id"],
        )
    indexes = {item["name"] for item in inspector.get_indexes("refresh_tokens")}
    if "ix_refresh_tokens_session_id" not in indexes:
        op.create_index(
            "ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"]
        )
    if "ix_refresh_tokens_user_session" not in indexes:
        op.create_index(
            "ix_refresh_tokens_user_session",
            "refresh_tokens",
            ["user_id", "session_id"],
        )
    op.execute("UPDATE refresh_tokens SET session_id = id WHERE session_id IS NULL")
    columns = {
        column["name"]: column
        for column in sa.inspect(bind).get_columns("refresh_tokens")
    }
    if columns["session_id"]["nullable"]:
        op.alter_column("refresh_tokens", "session_id", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_session", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens")
    op.drop_constraint(
        op.f("fk_refresh_tokens_login_history_id_login_histories"),
        "refresh_tokens",
        type_="foreignkey",
    )
    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "user_agent")
    op.drop_column("refresh_tokens", "browser")
    op.drop_column("refresh_tokens", "device")
    op.drop_column("refresh_tokens", "ip")
    op.drop_column("refresh_tokens", "login_history_id")
    op.drop_column("refresh_tokens", "session_id")