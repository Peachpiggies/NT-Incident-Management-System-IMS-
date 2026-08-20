"""Add tickets.escalation_locked_department_id / escalation_locked_tier.

Backs the "a tier can't reclaim a ticket it just escalated away, until
reassigned" rule: TicketEscalationService sets these on every escalation
(functional and technical), AssignmentService.claim() rejects a self-claim
from the locked department, and AssignmentService.assign_user() clears the
lock (a supervisor manually picking an assignee is a deliberate override).

Idempotent / guarded in the same style as 0019, in case this runs against a
database that was provisioned via create_all() after models.py already had
these columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_escalation_lock"
down_revision = "0019_attachment_mentions_fix"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    ticket_cols = _columns(bind, "tickets")

    if "escalation_locked_department_id" not in ticket_cols:
        op.add_column(
            "tickets",
            sa.Column(
                "escalation_locked_department_id",
                sa.Uuid(),
                sa.ForeignKey("departments.id"),
            ),
        )

    # Checked independently of the column guard above: a database that got
    # this column via create_all() (models.py declares it without
    # index=True) would have the column but not this index, so gating index
    # creation on column-existence alone would silently skip it forever.
    if "ix_tickets_escalation_locked_department_id" not in _indexes(bind, "tickets"):
        op.create_index(
            "ix_tickets_escalation_locked_department_id",
            "tickets",
            ["escalation_locked_department_id"],
        )

    if "escalation_locked_tier" not in ticket_cols:
        op.add_column(
            "tickets",
            sa.Column("escalation_locked_tier", sa.Integer()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    ticket_cols = _columns(bind, "tickets")

    if "escalation_locked_tier" in ticket_cols:
        op.drop_column("tickets", "escalation_locked_tier")

    # Checked independently of the column guard, same reasoning as upgrade():
    # the index and the column can be present/absent independently of each
    # other, so dropping the index must not be gated on the column check.
    if "ix_tickets_escalation_locked_department_id" in _indexes(bind, "tickets"):
        op.drop_index(
            "ix_tickets_escalation_locked_department_id", table_name="tickets"
        )

    if "escalation_locked_department_id" in ticket_cols:
        op.drop_column("tickets", "escalation_locked_department_id")