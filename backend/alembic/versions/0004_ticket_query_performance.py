"""Add ticket-number counter and operational query indexes.

Revision ID: 0004_ticket_query_performance
Revises: 0003_session_metadata
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_ticket_query_performance"
down_revision = "0003_session_metadata"
branch_labels = None
depends_on = None


def _index_names(bind, table_name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "ticket_number_sequences" not in inspector.get_table_names():
        op.create_table(
            "ticket_number_sequences",
            sa.Column("business_date", sa.Date(), nullable=False),
            sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("business_date", name="pk_ticket_number_sequences"),
        )
    indexes = _index_names(bind, "tickets")
    definitions = {
        "ix_tickets_requester_status_created": [
            "requester_id",
            "status_id",
            "created_at",
        ],
        "ix_tickets_assignee_status_created": [
            "assigned_to",
            "status_id",
            "created_at",
        ],
        "ix_tickets_category_priority": ["category_id", "priority_id"],
    }
    for name, columns in definitions.items():
        if name not in indexes:
            op.create_index(name, "tickets", columns)


def downgrade() -> None:
    bind = op.get_bind()
    indexes = _index_names(bind, "tickets")
    for name in [
        "ix_tickets_category_priority",
        "ix_tickets_assignee_status_created",
        "ix_tickets_requester_status_created",
    ]:
        if name in indexes:
            op.drop_index(name, table_name="tickets")
    if "ticket_number_sequences" in sa.inspect(bind).get_table_names():
        op.drop_table("ticket_number_sequences")
