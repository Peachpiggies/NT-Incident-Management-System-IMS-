"""Add the SLA engine persistence layer: policies, targets, ticket timers,
escalation triggers/events, and automatic pause rules.

app/services/sla_engine.py (policy matching, timer lifecycle, breach
detection, escalation firing) has existed since before this migration but
had no backing tables -- every ORM class it imported from app.db.models
(SLAPolicy, SLATarget, TicketSlaTimer, SLAEscalationTrigger,
SLAEscalationEvent) was undefined, so the module could not run. This
migration adds those tables plus a new one, sla_pause_rules, which did not
previously exist anywhere: the mapping of "which statuses automatically
pause a policy's timers" that app.services.sla_engine.apply_status_pause_rules
reads. Manual pause/resume (SLATimerPause/SLATimerResume endpoints, once
wired) already worked against ticket_sla_timers.status; this table is what
lets a status *transition* decide to pause/resume on its own instead of
requiring a person to click pause.

Revision ID: 0011_sla_engine
Revises: 0010_technical_escalation_reason
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_sla_engine"
down_revision = "0010_technical_escalation_reason"
branch_labels = None
depends_on = None


AUDIT_COLUMNS = (
    lambda: sa.Column("id", sa.Uuid(), primary_key=True),
    lambda: sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    lambda: sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
    lambda: sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    lambda: sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
    lambda: sa.Column("deleted_at", sa.DateTime(timezone=True)),
    lambda: sa.Column("deleted_by", sa.Uuid(), sa.ForeignKey("users.id")),
    lambda: sa.Column(
        "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
    ),
    lambda: sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
)


def _audit_columns() -> list[sa.Column]:
    return [col() for col in AUDIT_COLUMNS]


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # ---------------------------------------------------------------- #
    # sla_policies
    # ---------------------------------------------------------------- #
    if "sla_policies" not in tables:
        op.create_table(
            "sla_policies",
            *_audit_columns(),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id")),
            sa.Column(
                "category_id", sa.Uuid(), sa.ForeignKey("ticket_categories.id")
            ),
            sa.Column(
                "subcategory_id",
                sa.Uuid(),
                sa.ForeignKey("ticket_subcategories.id"),
            ),
            sa.Column("service_id", sa.Uuid(), sa.ForeignKey("ticket_services.id")),
            sa.Column(
                "priority_id", sa.Uuid(), sa.ForeignKey("ticket_priorities.id")
            ),
            sa.Column(
                "match_priority", sa.Integer(), nullable=False, server_default="100"
            ),
            sa.Column(
                "business_hours_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.UniqueConstraint("code", name="uq_sla_policies_code"),
        )
        op.create_index(
            "ix_sla_policies_active_match_priority",
            "sla_policies",
            ["is_active", "match_priority"],
        )
        op.create_index(
            "ix_sla_policies_department_id", "sla_policies", ["department_id"]
        )
        op.create_index(
            "ix_sla_policies_category_id", "sla_policies", ["category_id"]
        )
        op.create_index(
            "ix_sla_policies_subcategory_id", "sla_policies", ["subcategory_id"]
        )
        op.create_index("ix_sla_policies_service_id", "sla_policies", ["service_id"])
        op.create_index(
            "ix_sla_policies_priority_id", "sla_policies", ["priority_id"]
        )
        op.create_index("ix_sla_policies_is_deleted", "sla_policies", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # sla_targets
    # ---------------------------------------------------------------- #
    if "sla_targets" not in tables:
        op.create_table(
            "sla_targets",
            *_audit_columns(),
            sa.Column(
                "policy_id",
                sa.Uuid(),
                sa.ForeignKey("sla_policies.id"),
                nullable=False,
            ),
            sa.Column("metric_type", sa.String(length=20), nullable=False),
            sa.Column("target_minutes", sa.Integer(), nullable=False),
            sa.Column(
                "warning_threshold_pct",
                sa.Integer(),
                nullable=False,
                server_default="80",
            ),
            sa.UniqueConstraint(
                "policy_id", "metric_type", name="uq_sla_targets_policy_metric"
            ),
            sa.CheckConstraint(
                "metric_type IN ('RESPONSE', 'RESOLUTION')",
                name="ck_sla_targets_metric_type",
            ),
            sa.CheckConstraint(
                "warning_threshold_pct BETWEEN 1 AND 100",
                name="ck_sla_targets_warning_threshold_pct",
            ),
        )
        op.create_index("ix_sla_targets_policy_id", "sla_targets", ["policy_id"])
        op.create_index("ix_sla_targets_is_deleted", "sla_targets", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # sla_pause_rules  (new -- the actual "Pause/Resume Rules" node)
    # ---------------------------------------------------------------- #
    if "sla_pause_rules" not in tables:
        op.create_table(
            "sla_pause_rules",
            *_audit_columns(),
            sa.Column(
                "policy_id",
                sa.Uuid(),
                sa.ForeignKey("sla_policies.id"),
                nullable=False,
            ),
            sa.Column(
                "status_id",
                sa.Uuid(),
                sa.ForeignKey("ticket_statuses.id"),
                nullable=False,
            ),
            sa.Column("reason", sa.String(length=255)),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.UniqueConstraint(
                "policy_id", "status_id", name="uq_sla_pause_rules_policy_status"
            ),
        )
        op.create_index(
            "ix_sla_pause_rules_policy_id", "sla_pause_rules", ["policy_id"]
        )
        op.create_index(
            "ix_sla_pause_rules_status_id", "sla_pause_rules", ["status_id"]
        )
        op.create_index(
            "ix_sla_pause_rules_is_deleted", "sla_pause_rules", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # ticket_sla_timers
    # ---------------------------------------------------------------- #
    if "ticket_sla_timers" not in tables:
        op.create_table(
            "ticket_sla_timers",
            *_audit_columns(),
            sa.Column(
                "ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id"), nullable=False
            ),
            sa.Column(
                "policy_id",
                sa.Uuid(),
                sa.ForeignKey("sla_policies.id"),
                nullable=False,
            ),
            sa.Column("metric_type", sa.String(length=20), nullable=False),
            sa.Column("target_minutes", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="RUNNING",
            ),
            sa.Column("paused_at", sa.DateTime(timezone=True)),
            sa.Column(
                "total_paused_seconds",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "auto_paused_status_id",
                sa.Uuid(),
                sa.ForeignKey("ticket_statuses.id"),
            ),
            sa.Column("met_at", sa.DateTime(timezone=True)),
            sa.Column("breached_at", sa.DateTime(timezone=True)),
            sa.Column("cancelled_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint(
                "ticket_id",
                "metric_type",
                name="uq_ticket_sla_timers_ticket_metric",
            ),
            sa.CheckConstraint(
                "metric_type IN ('RESPONSE', 'RESOLUTION')",
                name="ck_ticket_sla_timers_metric_type",
            ),
            sa.CheckConstraint(
                "status IN ('RUNNING', 'PAUSED', 'MET', 'BREACHED', 'CANCELLED')",
                name="ck_ticket_sla_timers_status",
            ),
        )
        op.create_index(
            "ix_ticket_sla_timers_ticket_id", "ticket_sla_timers", ["ticket_id"]
        )
        op.create_index(
            "ix_ticket_sla_timers_policy_id", "ticket_sla_timers", ["policy_id"]
        )
        op.create_index(
            "ix_ticket_sla_timers_status_due",
            "ticket_sla_timers",
            ["status", "due_at"],
        )
        op.create_index(
            "ix_ticket_sla_timers_is_deleted", "ticket_sla_timers", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # sla_escalation_triggers
    # ---------------------------------------------------------------- #
    if "sla_escalation_triggers" not in tables:
        op.create_table(
            "sla_escalation_triggers",
            *_audit_columns(),
            sa.Column(
                "policy_id",
                sa.Uuid(),
                sa.ForeignKey("sla_policies.id"),
                nullable=False,
            ),
            sa.Column("trigger_on", sa.String(length=20), nullable=False),
            sa.Column("metric_type", sa.String(length=20)),
            sa.Column(
                "escalate_to_department_id", sa.Uuid(), sa.ForeignKey("departments.id")
            ),
            sa.Column("escalate_to_tier", sa.Integer()),
            sa.Column(
                "notify_user_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "notify_role_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "channels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.CheckConstraint(
                "trigger_on IN ('WARNING', 'BREACH')",
                name="ck_sla_escalation_triggers_trigger_on",
            ),
            sa.CheckConstraint(
                "metric_type IS NULL OR metric_type IN ('RESPONSE', 'RESOLUTION')",
                name="ck_sla_escalation_triggers_metric_type",
            ),
        )
        op.create_index(
            "ix_sla_escalation_triggers_policy_trigger_on",
            "sla_escalation_triggers",
            ["policy_id", "trigger_on"],
        )
        op.create_index(
            "ix_sla_escalation_triggers_is_deleted",
            "sla_escalation_triggers",
            ["is_deleted"],
        )

    # ---------------------------------------------------------------- #
    # sla_escalation_events
    # ---------------------------------------------------------------- #
    if "sla_escalation_events" not in tables:
        op.create_table(
            "sla_escalation_events",
            *_audit_columns(),
            sa.Column(
                "trigger_id",
                sa.Uuid(),
                sa.ForeignKey("sla_escalation_triggers.id"),
                nullable=False,
            ),
            sa.Column(
                "timer_id",
                sa.Uuid(),
                sa.ForeignKey("ticket_sla_timers.id"),
                nullable=False,
            ),
            sa.Column(
                "ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id"), nullable=False
            ),
            sa.Column("trigger_on", sa.String(length=20), nullable=False),
            sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "trigger_id",
                "timer_id",
                name="uq_sla_escalation_events_trigger_timer",
            ),
        )
        op.create_index(
            "ix_sla_escalation_events_trigger_id",
            "sla_escalation_events",
            ["trigger_id"],
        )
        op.create_index(
            "ix_sla_escalation_events_timer_id",
            "sla_escalation_events",
            ["timer_id"],
        )
        op.create_index(
            "ix_sla_escalation_events_ticket_id",
            "sla_escalation_events",
            ["ticket_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # Drop children before parents.
    for table in (
        "sla_escalation_events",
        "sla_escalation_triggers",
        "ticket_sla_timers",
        "sla_pause_rules",
        "sla_targets",
        "sla_policies",
    ):
        if table in tables:
            op.drop_table(table)
