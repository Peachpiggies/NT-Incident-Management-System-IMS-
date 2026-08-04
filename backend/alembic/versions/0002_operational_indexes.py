"""Add indexes used by operational ticket and audit queries.

Revision ID: 0002_operational_indexes
Revises: 0001_initial_schema
Create Date: 2026-08-04
"""

from alembic import op

revision = "0002_operational_indexes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tickets_status_assignee", "tickets", ["status_id", "assigned_to"])
    op.create_index("ix_ticket_assignments_ticket_assigned_at", "ticket_assignments", ["ticket_id", "assigned_at"])
    op.create_index("ix_ticket_histories_ticket_performed_at", "ticket_histories", ["ticket_id", "performed_at"])
    op.create_index("ix_activity_logs_resource", "activity_logs", ["resource", "resource_id"])
    op.create_index("ix_login_histories_user_login_at", "login_histories", ["user_id", "login_at"])


def downgrade() -> None:
    op.drop_index("ix_login_histories_user_login_at", table_name="login_histories")
    op.drop_index("ix_activity_logs_resource", table_name="activity_logs")
    op.drop_index("ix_ticket_histories_ticket_performed_at", table_name="ticket_histories")
    op.drop_index("ix_ticket_assignments_ticket_assigned_at", table_name="ticket_assignments")
    op.drop_index("ix_tickets_status_assignee", table_name="tickets")
