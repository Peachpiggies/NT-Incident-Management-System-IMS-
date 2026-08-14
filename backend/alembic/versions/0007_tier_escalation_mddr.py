"""Add tier tracking, MDDR checkpoints, SLA breach flag, and structured escalation history.

Revision ID: 0007_tier_escalation_mddr
Revises: 0006_workflow_transitions
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_tier_escalation_mddr"
down_revision = "0006_workflow_transitions"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    # --- tickets: tier + SLA breach flag + MDDR checkpoints -------------
    ticket_columns = _columns(bind, "tickets")
    if "current_tier" not in ticket_columns:
        op.add_column(
            "tickets",
            sa.Column(
                "current_tier", sa.Integer(), nullable=False, server_default="1"
            ),
        )
    if "sla_breached" not in ticket_columns:
        op.add_column(
            "tickets",
            sa.Column(
                "sla_breached",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "occurred_at" not in ticket_columns:
        op.add_column(
            "tickets", sa.Column("occurred_at", sa.DateTime(timezone=True))
        )
    if "detected_at" not in ticket_columns:
        op.add_column(
            "tickets", sa.Column("detected_at", sa.DateTime(timezone=True))
        )
    if "diagnosed_at" not in ticket_columns:
        op.add_column(
            "tickets", sa.Column("diagnosed_at", sa.DateTime(timezone=True))
        )

    if "ix_tickets_tier_status" not in _indexes(bind, "tickets"):
        op.create_index(
            "ix_tickets_tier_status", "tickets", ["current_tier", "status_id"]
        )

    # --- ticket_escalations: structured functional/technical history ----
    if "ticket_escalations" not in tables:
        op.create_table(
            "ticket_escalations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("deleted_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id"), nullable=False
            ),
            sa.Column("escalation_type", sa.String(length=20), nullable=False),
            sa.Column("from_tier", sa.Integer(), nullable=False),
            sa.Column("to_tier", sa.Integer(), nullable=False),
            sa.Column(
                "from_department_id", sa.Uuid(), sa.ForeignKey("departments.id")
            ),
            sa.Column("to_department_id", sa.Uuid(), sa.ForeignKey("departments.id")),
            sa.Column("reason_code", sa.String(length=50)),
            sa.Column("comment", sa.Text()),
            sa.Column("escalated_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column(
                "escalated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_ticket_escalations_ticket_id", "ticket_escalations", ["ticket_id"]
        )
        op.create_index(
            "ix_ticket_escalations_is_deleted", "ticket_escalations", ["is_deleted"]
        )
        op.create_index(
            "ix_ticket_escalations_ticket_escalated",
            "ticket_escalations",
            ["ticket_id", "escalated_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    if "ticket_escalations" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("ticket_escalations")

    indexes = _indexes(bind, "tickets")
    if "ix_tickets_tier_status" in indexes:
        op.drop_index("ix_tickets_tier_status", table_name="tickets")

    columns = _columns(bind, "tickets")
    for column in (
        "diagnosed_at",
        "detected_at",
        "occurred_at",
        "sla_breached",
        "current_tier",
    ):
        if column in columns:
            op.drop_column("tickets", column)
