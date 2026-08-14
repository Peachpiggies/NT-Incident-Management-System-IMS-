"""Require a reason from a controlled vocabulary on every technical escalation.

Technical escalation (T1 -> T2 -> T3) must be justified: the problem exceeds
the current tier's skill/access/complexity capability, or is at risk of
missing SLA/MDDR targets. This migration enforces that at the database level
as a backstop to the app-level validation in TicketEscalate (schema) and
escalate_ticket() (service layer) -- a row with escalation_type='TECHNICAL'
and a NULL or arbitrary reason_code can no longer be written, even via a
code path that bypasses those layers.

Functional escalations are unaffected: they are not constrained to this
vocabulary, since they're about routing to the right team rather than a
skill gap.

Revision ID: 0010_technical_escalation_reason
Revises: 0009_escalation_from_user
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_technical_escalation_reason"
down_revision = "0009_escalation_from_user"
branch_labels = None
depends_on = None

TECHNICAL_REASON_CODES = (
    "SKILL_REQUIRED",
    "COMPLEXITY",
    "ACCESS_REQUIRED",
    "SYSTEM_DEPENDENCY",
    "UNRESOLVED_AFTER_ATTEMPTS",
    "SLA_RISK",
    "MDDR_RISK",
)

CONSTRAINT_NAME = "ck_ticket_escalations_technical_requires_reason"


def _check_constraints(bind, table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_check_constraints(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if CONSTRAINT_NAME not in _check_constraints(bind, "ticket_escalations"):
        codes = ", ".join(f"'{code}'" for code in TECHNICAL_REASON_CODES)
        op.create_check_constraint(
            CONSTRAINT_NAME,
            "ticket_escalations",
            f"escalation_type <> 'TECHNICAL' OR "
            f"(reason_code IS NOT NULL AND reason_code IN ({codes}))",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if CONSTRAINT_NAME in _check_constraints(bind, "ticket_escalations"):
        op.drop_constraint(CONSTRAINT_NAME, "ticket_escalations", type_="check")
