"""Add the Problem Management persistence layer: problems, the daily
problem-number sequence, problem <-> incident links, workarounds, known
errors, and permanent fixes.

app/services/problem.py and app/api/v1/problem.py depend on six ORM
classes in app.db.models (Problem, ProblemNumberSequence,
ProblemIncidentLink, Workaround, KnownError, PermanentFix) that had no
backing tables until this migration.

This migration also retrofits the real FK from `root_causes.problem_id`
and `rca_reports.problem_id` to `problems.id`, now that `problems` exists
-- 0014_root_cause_analysis created those columns as plain UUIDs and its
docstring explicitly deferred this FK to whichever migration added
`problems`, rather than have either migration recreate the other's table.

Revision ID: 0015_problem_management
Revises: 0014_root_cause_analysis
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_problem_management"
down_revision = "0014_root_cause_analysis"
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


def _fk_names(bind, table: str) -> set[str]:
    return {fk["name"] for fk in sa.inspect(bind).get_foreign_keys(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # ---------------------------------------------------------------- #
    # problems
    # ---------------------------------------------------------------- #
    if "problems" not in tables:
        op.create_table(
            "problems",
            *_audit_columns(),
            sa.Column("problem_no", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "category_id",
                sa.Uuid(),
                sa.ForeignKey("ticket_categories.id"),
                nullable=False,
            ),
            sa.Column(
                "priority_id",
                sa.Uuid(),
                sa.ForeignKey("ticket_priorities.id"),
                nullable=False,
            ),
            sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id")),
            sa.Column(
                "status", sa.String(length=30), nullable=False, server_default="OPEN"
            ),
            sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("closed_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("problem_no", name=op.f("uq_problems_problem_no")),
            sa.CheckConstraint(
                "status IN ('OPEN', 'UNDER_INVESTIGATION', 'KNOWN_ERROR', 'RESOLVED', 'CLOSED')",
                name="ck_problems_status",
            ),
        )
        op.create_index("ix_problems_problem_no", "problems", ["problem_no"])
        op.create_index(
            "ix_problems_status_created", "problems", ["status", "created_at"]
        )
        op.create_index(
            "ix_problems_category_priority", "problems", ["category_id", "priority_id"]
        )
        op.create_index("ix_problems_category_id", "problems", ["category_id"])
        op.create_index("ix_problems_priority_id", "problems", ["priority_id"])
        op.create_index("ix_problems_department_id", "problems", ["department_id"])
        op.create_index("ix_problems_owner_id", "problems", ["owner_id"])
        op.create_index("ix_problems_is_deleted", "problems", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # problem_number_sequences
    # ---------------------------------------------------------------- #
    if "problem_number_sequences" not in tables:
        op.create_table(
            "problem_number_sequences",
            sa.Column("business_date", sa.Date(), primary_key=True),
            sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
        )

    # ---------------------------------------------------------------- #
    # problem_incident_links
    # ---------------------------------------------------------------- #
    if "problem_incident_links" not in tables:
        op.create_table(
            "problem_incident_links",
            *_audit_columns(),
            sa.Column(
                "problem_id", sa.Uuid(), sa.ForeignKey("problems.id"), nullable=False
            ),
            sa.Column(
                "ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id"), nullable=False
            ),
            sa.Column("note", sa.String(length=500)),
            sa.Column(
                "linked_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "linked_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "problem_id",
                "ticket_id",
                name=op.f("uq_problem_incident_links_pair"),
            ),
        )
        op.create_index(
            "ix_problem_incident_links_problem_id",
            "problem_incident_links",
            ["problem_id"],
        )
        op.create_index(
            "ix_problem_incident_links_ticket_id",
            "problem_incident_links",
            ["ticket_id"],
        )
        op.create_index(
            "ix_problem_incident_links_is_deleted",
            "problem_incident_links",
            ["is_deleted"],
        )

    # ---------------------------------------------------------------- #
    # workarounds
    # ---------------------------------------------------------------- #
    if "workarounds" not in tables:
        op.create_table(
            "workarounds",
            *_audit_columns(),
            sa.Column(
                "problem_id", sa.Uuid(), sa.ForeignKey("problems.id"), nullable=False
            ),
            sa.Column("description", sa.String(length=4000), nullable=False),
            sa.Column("steps", sa.Text()),
            sa.Column(
                "is_temporary", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "effectiveness",
                sa.String(length=20),
                nullable=False,
                server_default="UNVERIFIED",
            ),
            sa.CheckConstraint(
                "effectiveness IN ('UNVERIFIED', 'PARTIAL', 'EFFECTIVE', 'INEFFECTIVE')",
                name="ck_workarounds_effectiveness",
            ),
        )
        op.create_index(
            "ix_workarounds_problem_id", "workarounds", ["problem_id"]
        )
        op.create_index("ix_workarounds_is_deleted", "workarounds", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # known_errors
    # ---------------------------------------------------------------- #
    if "known_errors" not in tables:
        op.create_table(
            "known_errors",
            *_audit_columns(),
            sa.Column(
                "problem_id", sa.Uuid(), sa.ForeignKey("problems.id"), nullable=False
            ),
            sa.Column("symptoms", sa.String(length=4000), nullable=False),
            sa.Column("root_cause_summary", sa.String(length=4000)),
            sa.Column("workaround_id", sa.Uuid(), sa.ForeignKey("workarounds.id")),
            sa.Column(
                "is_published_to_kb",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("kb_article_id", sa.Uuid(), sa.ForeignKey("kb_articles.id")),
        )
        op.create_index(
            "ix_known_errors_problem_id", "known_errors", ["problem_id"]
        )
        op.create_index("ix_known_errors_is_deleted", "known_errors", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # permanent_fixes
    # ---------------------------------------------------------------- #
    if "permanent_fixes" not in tables:
        op.create_table(
            "permanent_fixes",
            *_audit_columns(),
            sa.Column(
                "problem_id", sa.Uuid(), sa.ForeignKey("problems.id"), nullable=False
            ),
            # No FK yet: change management has no ORM table/migration -- see
            # app.db.models.PermanentFix docstring.
            sa.Column("change_request_id", sa.Uuid()),
            sa.Column("description", sa.String(length=4000), nullable=False),
            sa.Column("implemented_at", sa.DateTime(timezone=True)),
            sa.Column("verified_by_id", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("verified_at", sa.DateTime(timezone=True)),
        )
        op.create_index(
            "ix_permanent_fixes_problem_id", "permanent_fixes", ["problem_id"]
        )
        op.create_index(
            "ix_permanent_fixes_is_deleted", "permanent_fixes", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # Retrofit FK: root_causes.problem_id / rca_reports.problem_id -> problems.id
    # ---------------------------------------------------------------- #
    # Wrapped in op.f() per the naming_convention in app/db/session.py: the
    # "fk" convention there has no %(constraint_name)s token so it wouldn't
    # double-prefix like "ck" does, but op.f() is still the correct way to
    # hand Alembic a literal name for a standalone op.create_foreign_key
    # call rather than relying on its own generated one.
    if "root_causes" in tables and not (
        {"fk_root_causes_problem_id_problems"} & _fk_names(bind, "root_causes")
    ):
        op.create_foreign_key(
            op.f("fk_root_causes_problem_id_problems"),
            "root_causes",
            "problems",
            ["problem_id"],
            ["id"],
        )
    if "rca_reports" in tables and not (
        {"fk_rca_reports_problem_id_problems"} & _fk_names(bind, "rca_reports")
    ):
        op.create_foreign_key(
            op.f("fk_rca_reports_problem_id_problems"),
            "rca_reports",
            "problems",
            ["problem_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "rca_reports" in tables and (
        {"fk_rca_reports_problem_id_problems"} & _fk_names(bind, "rca_reports")
    ):
        op.drop_constraint(
            op.f("fk_rca_reports_problem_id_problems"),
            "rca_reports",
            type_="foreignkey",
        )
    if "root_causes" in tables and (
        {"fk_root_causes_problem_id_problems"} & _fk_names(bind, "root_causes")
    ):
        op.drop_constraint(
            op.f("fk_root_causes_problem_id_problems"),
            "root_causes",
            type_="foreignkey",
        )

    # Drop children before parents.
    for table in (
        "permanent_fixes",
        "known_errors",
        "workarounds",
        "problem_incident_links",
        "problem_number_sequences",
        "problems",
    ):
        if table in tables:
            op.drop_table(table)
