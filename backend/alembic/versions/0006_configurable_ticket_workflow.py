"""Add configurable allowed transitions for ticket workflow.

Revision ID: 0006_configurable_ticket_workflow
Revises: 0005_ticket_classification_assignment
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_configurable_ticket_workflow"
down_revision = "0005_ticket_classification_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "ticket_status_transitions" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "ticket_status_transitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("from_status_id", sa.Uuid(), sa.ForeignKey("ticket_statuses.id"), nullable=False),
        sa.Column("to_status_id", sa.Uuid(), sa.ForeignKey("ticket_statuses.id"), nullable=False),
        sa.Column("required_permission", sa.String(length=200)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("from_status_id", "to_status_id", name="uq_ticket_status_transitions_edge"),
    )
    op.create_index("ix_ticket_status_transitions_from_status_id", "ticket_status_transitions", ["from_status_id"])
    op.create_index("ix_ticket_status_transitions_to_status_id", "ticket_status_transitions", ["to_status_id"])
    op.create_index("ix_ticket_status_transitions_is_deleted", "ticket_status_transitions", ["is_deleted"])
    op.create_index("ix_ticket_status_transitions_from_active", "ticket_status_transitions", ["from_status_id", "is_active"])


def downgrade() -> None:
    bind = op.get_bind()
    if "ticket_status_transitions" in sa.inspect(bind).get_table_names():
        op.drop_table("ticket_status_transitions")
