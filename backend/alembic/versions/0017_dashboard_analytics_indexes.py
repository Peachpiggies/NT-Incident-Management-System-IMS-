"""Indexes supporting dashboard, KPI, report, and export queries."""

from alembic import op

revision = "0017_dashboard_analytics_indexes"
down_revision = "0016_change_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ticket_histories_ticket_action_performed",
        "ticket_histories",
        ["ticket_id", "action", "performed_at"],
    )
    op.create_index(
        "ix_ticket_sla_timers_started_status",
        "ticket_sla_timers",
        ["started_at", "status"],
    )
    op.create_index(
        "ix_change_requests_created_status",
        "change_requests",
        ["created_at", "status"],
    )
    op.create_index(
        "ix_activity_logs_created_module",
        "activity_logs",
        ["created_at", "module"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_logs_created_module", table_name="activity_logs")
    op.drop_index("ix_change_requests_created_status", table_name="change_requests")
    op.drop_index("ix_ticket_sla_timers_started_status", table_name="ticket_sla_timers")
    op.drop_index("ix_ticket_histories_ticket_action_performed", table_name="ticket_histories")
