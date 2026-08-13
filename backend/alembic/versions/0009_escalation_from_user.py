"""Track the assignee handed off at escalation time, and enforce the
Functional-vs-Technical escalation distinction at the database level.

Functional escalation = re-routing to a more appropriate team, not
necessarily a tier change (e.g. Tier-1 Helpdesk -> Billing Dept, still tier
1). Technical escalation = moving up the expertise chain (T1 -> T2 -> T3).
These have different validity rules and must not be conflated:

  - FUNCTIONAL rows must always specify to_department_id.
  - TECHNICAL rows must always have to_tier > from_tier.

Revision ID: 0009_escalation_from_user
Revises: 0008_ticket_comment_update_type
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_escalation_from_user"
down_revision = "0008_ticket_comment_update_type"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def _check_constraints(bind, table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_check_constraints(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    columns = _columns(bind, "ticket_escalations")
    if "from_user_id" not in columns:
        op.add_column(
            "ticket_escalations",
            sa.Column("from_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        )

    indexes = _indexes(bind, "ticket_escalations")
    if "ix_ticket_escalations_from_user_id" not in indexes:
        op.create_index(
            "ix_ticket_escalations_from_user_id", "ticket_escalations", ["from_user_id"]
        )
    if "ix_ticket_escalations_ticket_type" not in indexes:
        op.create_index(
            "ix_ticket_escalations_ticket_type",
            "ticket_escalations",
            ["ticket_id", "escalation_type"],
        )

    checks = _check_constraints(bind, "ticket_escalations")
    if "ck_ticket_escalations_functional_requires_department" not in checks:
        op.create_check_constraint(
            "ck_ticket_escalations_functional_requires_department",
            "ticket_escalations",
            "escalation_type <> 'FUNCTIONAL' OR to_department_id IS NOT NULL",
        )
    if "ck_ticket_escalations_technical_requires_tier_increase" not in checks:
        op.create_check_constraint(
            "ck_ticket_escalations_technical_requires_tier_increase",
            "ticket_escalations",
            "escalation_type <> 'TECHNICAL' OR to_tier > from_tier",
        )


def downgrade() -> None:
    bind = op.get_bind()

    checks = _check_constraints(bind, "ticket_escalations")
    if "ck_ticket_escalations_technical_requires_tier_increase" in checks:
        op.drop_constraint(
            "ck_ticket_escalations_technical_requires_tier_increase",
            "ticket_escalations",
            type_="check",
        )
    if "ck_ticket_escalations_functional_requires_department" in checks:
        op.drop_constraint(
            "ck_ticket_escalations_functional_requires_department",
            "ticket_escalations",
            type_="check",
        )

    indexes = _indexes(bind, "ticket_escalations")
    if "ix_ticket_escalations_ticket_type" in indexes:
        op.drop_index("ix_ticket_escalations_ticket_type", table_name="ticket_escalations")
    if "ix_ticket_escalations_from_user_id" in indexes:
        op.drop_index("ix_ticket_escalations_from_user_id", table_name="ticket_escalations")

    columns = _columns(bind, "ticket_escalations")
    if "from_user_id" in columns:
        op.drop_column("ticket_escalations", "from_user_id")
