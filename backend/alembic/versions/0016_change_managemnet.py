"""Add Change Management persistence and link permanent fixes to changes.

Revision ID: 0016_change_management
Revises: 0015_problem_management
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_change_management"
down_revision = "0015_problem_management"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "change_number_sequences" not in tables:
        op.create_table(
            "change_number_sequences",
            sa.Column("business_date", sa.Date(), primary_key=True),
            sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
        )

    if "change_requests" not in tables:
        op.create_table(
            "change_requests",
            *_audit_columns(),
            sa.Column("change_no", sa.String(32), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("change_type", sa.String(20), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
            sa.Column("priority_id", sa.Uuid(), sa.ForeignKey("ticket_priorities.id"), nullable=False),
            sa.Column("service_id", sa.Uuid(), sa.ForeignKey("ticket_services.id")),
            sa.Column("problem_id", sa.Uuid(), sa.ForeignKey("problems.id")),
            sa.Column("requested_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("risk_level", sa.String(20)),
            sa.Column("emergency_justification", sa.Text()),
            sa.Column("planned_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("planned_end", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("change_no", name=op.f("uq_change_requests_change_no")),
            sa.CheckConstraint(
                "change_type IN ('STANDARD', 'NORMAL', 'EMERGENCY')",
                name=op.f("ck_change_requests_type"),
            ),
            sa.CheckConstraint(
                "status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SCHEDULED', "
                "'IN_PROGRESS', 'IMPLEMENTED', 'VALIDATED', 'FAILED', 'ROLLED_BACK', 'CLOSED')",
                name=op.f("ck_change_requests_status"),
            ),
        )
        for name, cols in (
            ("ix_change_requests_change_no", ["change_no"]),
            ("ix_change_requests_status_created", ["status", "created_at"]),
            ("ix_change_requests_requested_by", ["requested_by_id"]),
            ("ix_change_requests_problem_id", ["problem_id"]),
            ("ix_change_requests_service_id", ["service_id"]),
            ("ix_change_requests_priority_id", ["priority_id"]),
            ("ix_change_requests_is_deleted", ["is_deleted"]),
        ):
            op.create_index(name, "change_requests", cols)

    if "change_risk_assessments" not in tables:
        op.create_table(
            "change_risk_assessments",
            *_audit_columns(),
            sa.Column("change_request_id", sa.Uuid(), sa.ForeignKey("change_requests.id"), nullable=False),
            sa.Column("risk_level", sa.String(20), nullable=False),
            sa.Column("impact_description", sa.Text(), nullable=False),
            sa.Column("likelihood", sa.String(100), nullable=False),
            sa.Column("mitigation_plan", sa.Text()),
            sa.Column("assessed_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.UniqueConstraint("change_request_id", name=op.f("uq_change_risk_assessments_change")),
            sa.CheckConstraint(
                "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
                name=op.f("ck_change_risk_assessments_level"),
            ),
        )
        op.create_index("ix_change_risk_assessments_change_request_id", "change_risk_assessments", ["change_request_id"])
        op.create_index("ix_change_risk_assessments_is_deleted", "change_risk_assessments", ["is_deleted"])

    if "change_approvals" not in tables:
        op.create_table(
            "change_approvals",
            *_audit_columns(),
            sa.Column("change_request_id", sa.Uuid(), sa.ForeignKey("change_requests.id"), nullable=False),
            sa.Column("approver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("decision", sa.String(20), nullable=False),
            sa.Column("comments", sa.Text()),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("change_request_id", "approver_id", name=op.f("uq_change_approvals_change_approver")),
            sa.CheckConstraint(
                "decision IN ('PENDING', 'APPROVED', 'REJECTED')",
                name=op.f("ck_change_approvals_decision"),
            ),
        )
        op.create_index("ix_change_approvals_change_request_id", "change_approvals", ["change_request_id"])
        op.create_index("ix_change_approvals_approver_id", "change_approvals", ["approver_id"])
        op.create_index("ix_change_approvals_is_deleted", "change_approvals", ["is_deleted"])

    if "change_implementations" not in tables:
        op.create_table(
            "change_implementations",
            *_audit_columns(),
            sa.Column("change_request_id", sa.Uuid(), sa.ForeignKey("change_requests.id"), nullable=False),
            sa.Column("implementation_plan", sa.Text(), nullable=False),
            sa.Column("implemented_by_id", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("scheduled_start", sa.DateTime(timezone=True)),
            sa.Column("scheduled_end", sa.DateTime(timezone=True)),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("notes", sa.Text()),
            sa.UniqueConstraint("change_request_id", name=op.f("uq_change_implementations_change")),
        )
        op.create_index("ix_change_implementations_change_request_id", "change_implementations", ["change_request_id"])
        op.create_index("ix_change_implementations_is_deleted", "change_implementations", ["is_deleted"])

    if "change_validations" not in tables:
        op.create_table(
            "change_validations",
            *_audit_columns(),
            sa.Column("change_request_id", sa.Uuid(), sa.ForeignKey("change_requests.id"), nullable=False),
            sa.Column("validated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("validation_result", sa.Boolean(), nullable=False),
            sa.Column("notes", sa.Text()),
            sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("change_request_id", name=op.f("uq_change_validations_change")),
        )
        op.create_index("ix_change_validations_change_request_id", "change_validations", ["change_request_id"])
        op.create_index("ix_change_validations_is_deleted", "change_validations", ["is_deleted"])

    if "change_rollbacks" not in tables:
        op.create_table(
            "change_rollbacks",
            *_audit_columns(),
            sa.Column("change_request_id", sa.Uuid(), sa.ForeignKey("change_requests.id"), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("rollback_plan", sa.Text(), nullable=False),
            sa.Column("initiated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("change_request_id", name=op.f("uq_change_rollbacks_change")),
        )
        op.create_index("ix_change_rollbacks_change_request_id", "change_rollbacks", ["change_request_id"])
        op.create_index("ix_change_rollbacks_is_deleted", "change_rollbacks", ["is_deleted"])

    # 0015 intentionally left this column without an FK because Change
    # Management did not yet have a persistence layer.
    if "permanent_fixes" in tables:
        fk_names = {fk["name"] for fk in inspector.get_foreign_keys("permanent_fixes")}
        if "fk_permanent_fixes_change_request_id_change_requests" not in fk_names:
            with op.batch_alter_table("permanent_fixes") as batch:
                batch.create_foreign_key(
                    op.f("fk_permanent_fixes_change_request_id_change_requests"),
                    "change_requests",
                    ["change_request_id"],
                    ["id"],
                )
            op.create_index(
                "ix_permanent_fixes_change_request_id",
                "permanent_fixes",
                ["change_request_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "permanent_fixes" in tables:
        fk_names = {fk["name"] for fk in inspector.get_foreign_keys("permanent_fixes")}
        if "fk_permanent_fixes_change_request_id_change_requests" in fk_names:
            with op.batch_alter_table("permanent_fixes") as batch:
                batch.drop_constraint(
                    op.f("fk_permanent_fixes_change_request_id_change_requests"),
                    type_="foreignkey",
                )
        indexes = {i["name"] for i in inspector.get_indexes("permanent_fixes")}
        if "ix_permanent_fixes_change_request_id" in indexes:
            op.drop_index("ix_permanent_fixes_change_request_id", table_name="permanent_fixes")

    for table in (
        "change_rollbacks",
        "change_validations",
        "change_implementations",
        "change_approvals",
        "change_risk_assessments",
        "change_requests",
        "change_number_sequences",
    ):
        if table in tables:
            op.drop_table(table)
