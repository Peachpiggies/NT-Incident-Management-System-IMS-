"""Add the Root Cause Analysis persistence layer: root causes, contributing
factors, impact analysis, and the RCA report itself.

app/services/rca.py and app/api/v1/rca.py depend on four ORM classes in
app.db.models (RootCause, ContributingFactor, ImpactAnalysis, RCAReport)
that had no backing tables until this migration.

`root_causes.problem_id` and `rca_reports.problem_id` are plain UUID
columns with no FK constraint: the `problems` table doesn't exist yet. The
Problem Management migration should add
`op.create_foreign_key(..., "problems", ["problem_id"], ["id"])` on both
tables once it creates `problems`, rather than recreating either table.

Revision ID: 0014_root_cause_analysis
Revises: 0013_notification_engine
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_root_cause_analysis"
down_revision = "0013_notification_engine"
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
    # root_causes
    # ---------------------------------------------------------------- #
    if "root_causes" not in tables:
        op.create_table(
            "root_causes",
            *_audit_columns(),
            sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id")),
            sa.Column("problem_id", sa.Uuid()),
            sa.Column("category", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "identified_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.CheckConstraint(
                "ticket_id IS NOT NULL OR problem_id IS NOT NULL",
                name="ck_root_causes_anchor",
            ),
        )
        op.create_index("ix_root_causes_ticket_id", "root_causes", ["ticket_id"])
        op.create_index("ix_root_causes_problem_id", "root_causes", ["problem_id"])
        op.create_index(
            "ix_root_causes_identified_by_id", "root_causes", ["identified_by_id"]
        )
        op.create_index("ix_root_causes_is_deleted", "root_causes", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # contributing_factors
    # ---------------------------------------------------------------- #
    if "contributing_factors" not in tables:
        op.create_table(
            "contributing_factors",
            *_audit_columns(),
            sa.Column(
                "root_cause_id", sa.Uuid(), sa.ForeignKey("root_causes.id"), nullable=False
            ),
            sa.Column("factor_type", sa.String(length=100), nullable=False),
            sa.Column("description", sa.String(length=2000), nullable=False),
        )
        op.create_index(
            "ix_contributing_factors_root_cause_id",
            "contributing_factors",
            ["root_cause_id"],
        )
        op.create_index(
            "ix_contributing_factors_is_deleted", "contributing_factors", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # impact_analyses
    # ---------------------------------------------------------------- #
    if "impact_analyses" not in tables:
        op.create_table(
            "impact_analyses",
            *_audit_columns(),
            sa.Column(
                "root_cause_id", sa.Uuid(), sa.ForeignKey("root_causes.id"), nullable=False
            ),
            sa.Column(
                "affected_service_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "affected_users_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "downtime_minutes", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "business_impact",
                sa.String(length=20),
                nullable=False,
                server_default="LOW",
            ),
            sa.Column("financial_impact", sa.Numeric(14, 2)),
            sa.Column("notes", sa.String(length=2000)),
            sa.CheckConstraint(
                "business_impact IN ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'SEVERE')",
                name="ck_impact_analyses_business_impact",
            ),
        )
        op.create_index(
            "ix_impact_analyses_root_cause_id", "impact_analyses", ["root_cause_id"]
        )
        op.create_index(
            "ix_impact_analyses_is_deleted", "impact_analyses", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # rca_reports
    # ---------------------------------------------------------------- #
    if "rca_reports" not in tables:
        op.create_table(
            "rca_reports",
            *_audit_columns(),
            sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id")),
            sa.Column("problem_id", sa.Uuid()),
            sa.Column(
                "root_cause_id", sa.Uuid(), sa.ForeignKey("root_causes.id"), nullable=False
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("timeline", sa.Text()),
            sa.Column("corrective_actions", sa.String(length=4000)),
            sa.Column("preventive_actions", sa.String(length=4000)),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="DRAFT"
            ),
            sa.Column(
                "prepared_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column("approved_by_id", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("approved_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint(
                "ticket_id IS NOT NULL OR problem_id IS NOT NULL",
                name="ck_rca_reports_anchor",
            ),
            sa.CheckConstraint(
                "status IN ('DRAFT', 'IN_REVIEW', 'APPROVED')",
                name="ck_rca_reports_status",
            ),
        )
        op.create_index("ix_rca_reports_ticket_id", "rca_reports", ["ticket_id"])
        op.create_index("ix_rca_reports_problem_id", "rca_reports", ["problem_id"])
        op.create_index(
            "ix_rca_reports_root_cause_id", "rca_reports", ["root_cause_id"]
        )
        op.create_index(
            "ix_rca_reports_prepared_by_id", "rca_reports", ["prepared_by_id"]
        )
        op.create_index("ix_rca_reports_is_deleted", "rca_reports", ["is_deleted"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # Drop children before parents.
    for table in (
        "rca_reports",
        "impact_analyses",
        "contributing_factors",
        "root_causes",
    ):
        if table in tables:
            op.drop_table(table)