"""Distinguish technical updates from general internal notes on ticket comments.

Adds `ticket_comments.update_type` (NOTE / TECHNICAL_UPDATE) so the Tier 2/3
investigation timeline can be queried separately from general internal chatter.
Team ownership continues to be tracked via `ticket_escalations.from_department_id`
/ `to_department_id` (added in 0007) plus `tickets.department_id` as the current
owner; no new ownership table is introduced.

Revision ID: 0008_ticket_comment_update_type
Revises: 0007_tier_escalation_mddr
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_ticket_comment_update_type"
down_revision = "0007_tier_escalation_mddr"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    columns = _columns(bind, "ticket_comments")
    if "update_type" not in columns:
        op.add_column(
            "ticket_comments",
            sa.Column(
                "update_type",
                sa.String(length=20),
                nullable=False,
                server_default="NOTE",
            ),
        )

    if "ix_ticket_comments_ticket_update_type" not in _indexes(bind, "ticket_comments"):
        op.create_index(
            "ix_ticket_comments_ticket_update_type",
            "ticket_comments",
            ["ticket_id", "update_type"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    indexes = _indexes(bind, "ticket_comments")
    if "ix_ticket_comments_ticket_update_type" in indexes:
        op.drop_index(
            "ix_ticket_comments_ticket_update_type", table_name="ticket_comments"
        )

    columns = _columns(bind, "ticket_comments")
    if "update_type" in columns:
        op.drop_column("ticket_comments", "update_type")
