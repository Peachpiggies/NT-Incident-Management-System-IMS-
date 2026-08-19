"""Add the Notification Engine persistence layer.

Also creates the `notifications` table itself: despite the `Notification`
ORM model existing since the initial schema, no earlier migration ever
created it -- a pre-existing gap, unrelated to this feature, closed here
because the rest of the engine (NotificationHistory.notification_id) has a
foreign key into it.

New tables: notifications, notification_rules, escalation_notifications,
notification_history.

Revision ID: 0013_notification_engine
Revises: 0012_knowledge_base
Create Date: 2026-08-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_notification_engine"
down_revision = "0012_knowledge_base"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # ---------------------------------------------------------------- #
    # notifications (pre-existing model, never had a migration)
    # ---------------------------------------------------------------- #
    if "notifications" not in tables:
        op.create_table(
            "notifications",
            *_audit_columns(),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("message", sa.String(length=500), nullable=False),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column(
                "is_read", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("read_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
        op.create_index("ix_notifications_is_deleted", "notifications", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # notification_rules
    # ---------------------------------------------------------------- #
    if "notification_rules" not in tables:
        op.create_table(
            "notification_rules",
            *_audit_columns(),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column(
                "channels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column(
                "recipient_role_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "recipient_user_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column("template_id", sa.Uuid()),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
        )
        op.create_index(
            "ix_notification_rules_event_type", "notification_rules", ["event_type"]
        )
        op.create_index(
            "ix_notification_rules_is_deleted", "notification_rules", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # escalation_notifications
    # ---------------------------------------------------------------- #
    if "escalation_notifications" not in tables:
        op.create_table(
            "escalation_notifications",
            *_audit_columns(),
            sa.Column(
                "ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id"), nullable=False
            ),
            sa.Column(
                "escalation_trigger_id",
                sa.Uuid(),
                sa.ForeignKey("sla_escalation_triggers.id"),
                nullable=False,
            ),
            sa.Column("channel", sa.String(length=20), nullable=False),
            sa.Column(
                "recipient_user_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column("message", sa.String(length=2000), nullable=False),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="pending"
            ),
            sa.Column("sent_at", sa.DateTime(timezone=True)),
        )
        op.create_index(
            "ix_escalation_notifications_ticket_id",
            "escalation_notifications",
            ["ticket_id"],
        )
        op.create_index(
            "ix_escalation_notifications_escalation_trigger_id",
            "escalation_notifications",
            ["escalation_trigger_id"],
        )
        op.create_index(
            "ix_escalation_notifications_is_deleted",
            "escalation_notifications",
            ["is_deleted"],
        )

    # ---------------------------------------------------------------- #
    # notification_history
    # ---------------------------------------------------------------- #
    if "notification_history" not in tables:
        op.create_table(
            "notification_history",
            *_audit_columns(),
            sa.Column("notification_id", sa.Uuid(), sa.ForeignKey("notifications.id")),
            sa.Column(
                "escalation_notification_id",
                sa.Uuid(),
                sa.ForeignKey("escalation_notifications.id"),
            ),
            sa.Column("channel", sa.String(length=20), nullable=False),
            sa.Column(
                "recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="pending"
            ),
            sa.Column("error_message", sa.String(length=1000)),
            sa.Column("sent_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint(
                "NOT (notification_id IS NOT NULL AND escalation_notification_id IS NOT NULL)",
                name="ck_notification_history_not_both_sources",
            ),
        )
        op.create_index(
            "ix_notification_history_notification_id",
            "notification_history",
            ["notification_id"],
        )
        op.create_index(
            "ix_notification_history_escalation_notification_id",
            "notification_history",
            ["escalation_notification_id"],
        )
        op.create_index(
            "ix_notification_history_recipient_user_id",
            "notification_history",
            ["recipient_user_id"],
        )
        op.create_index(
            "ix_notification_history_is_deleted", "notification_history", ["is_deleted"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    for table in (
        "notification_history",
        "escalation_notifications",
        "notification_rules",
        "notifications",
    ):
        if table in tables:
            op.drop_table(table)
