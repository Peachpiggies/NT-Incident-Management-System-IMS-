"""Add the Knowledge Base persistence layer: configurable article-status
workflow (mirroring ticket_statuses / ticket_status_transitions),
categories, articles, version snapshots, and article <-> incident links.

app/services/knowledge_base.py and app/api/v1/knowledge_base.py depend on
six ORM classes in app.db.models (KBArticleStatus,
KBArticleStatusTransition, KBCategory, KBArticle, KBArticleVersion,
KBArticleIncidentLink) that had no backing tables until this migration.

Revision ID: 0012_knowledge_base
Revises: 0011_sla_engine
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_knowledge_base"
down_revision = "0011_sla_engine"
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
    # kb_article_statuses
    # ---------------------------------------------------------------- #
    if "kb_article_statuses" not in tables:
        op.create_table(
            "kb_article_statuses",
            *_audit_columns(),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("color", sa.String(length=20)),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.UniqueConstraint("code", name="uq_kb_article_statuses_code"),
        )
        op.create_index(
            "ix_kb_article_statuses_is_deleted", "kb_article_statuses", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # kb_article_status_transitions
    # ---------------------------------------------------------------- #
    if "kb_article_status_transitions" not in tables:
        op.create_table(
            "kb_article_status_transitions",
            *_audit_columns(),
            sa.Column(
                "from_status_id",
                sa.Uuid(),
                sa.ForeignKey("kb_article_statuses.id"),
                nullable=False,
            ),
            sa.Column(
                "to_status_id",
                sa.Uuid(),
                sa.ForeignKey("kb_article_statuses.id"),
                nullable=False,
            ),
            sa.Column("required_permission", sa.String(length=200)),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.UniqueConstraint(
                "from_status_id",
                "to_status_id",
                name="uq_kb_article_status_transitions_edge",
            ),
        )
        op.create_index(
            "ix_kb_article_status_transitions_from_status_id",
            "kb_article_status_transitions",
            ["from_status_id"],
        )
        op.create_index(
            "ix_kb_article_status_transitions_to_status_id",
            "kb_article_status_transitions",
            ["to_status_id"],
        )
        op.create_index(
            "ix_kb_article_status_transitions_from_active",
            "kb_article_status_transitions",
            ["from_status_id", "is_active"],
        )
        op.create_index(
            "ix_kb_article_status_transitions_is_deleted",
            "kb_article_status_transitions",
            ["is_deleted"],
        )

    # ---------------------------------------------------------------- #
    # kb_categories
    # ---------------------------------------------------------------- #
    if "kb_categories" not in tables:
        op.create_table(
            "kb_categories",
            *_audit_columns(),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("kb_categories.id")),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
        )
        op.create_index("ix_kb_categories_parent_id", "kb_categories", ["parent_id"])
        op.create_index(
            "ix_kb_categories_is_deleted", "kb_categories", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # kb_articles
    # ---------------------------------------------------------------- #
    if "kb_articles" not in tables:
        op.create_table(
            "kb_articles",
            *_audit_columns(),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.String(length=500)),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "category_id",
                sa.Uuid(),
                sa.ForeignKey("kb_categories.id"),
                nullable=False,
            ),
            sa.Column(
                "tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column(
                "status_id",
                sa.Uuid(),
                sa.ForeignKey("kb_article_statuses.id"),
                nullable=False,
            ),
            sa.Column(
                "current_version_no",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "view_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("published_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_kb_articles_category_id", "kb_articles", ["category_id"])
        op.create_index("ix_kb_articles_status_id", "kb_articles", ["status_id"])
        op.create_index("ix_kb_articles_author_id", "kb_articles", ["author_id"])
        op.create_index(
            "ix_kb_articles_status_category", "kb_articles", ["status_id", "category_id"]
        )
        op.create_index("ix_kb_articles_is_deleted", "kb_articles", ["is_deleted"])

    # ---------------------------------------------------------------- #
    # kb_article_versions
    # ---------------------------------------------------------------- #
    if "kb_article_versions" not in tables:
        op.create_table(
            "kb_article_versions",
            *_audit_columns(),
            sa.Column(
                "article_id", sa.Uuid(), sa.ForeignKey("kb_articles.id"), nullable=False
            ),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("change_summary", sa.String(length=500)),
            sa.Column(
                "changed_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.UniqueConstraint(
                "article_id", "version_no", name="uq_kb_article_versions_article_no"
            ),
        )
        op.create_index(
            "ix_kb_article_versions_article_id", "kb_article_versions", ["article_id"]
        )
        op.create_index(
            "ix_kb_article_versions_is_deleted", "kb_article_versions", ["is_deleted"]
        )

    # ---------------------------------------------------------------- #
    # kb_article_incident_links
    # ---------------------------------------------------------------- #
    if "kb_article_incident_links" not in tables:
        op.create_table(
            "kb_article_incident_links",
            *_audit_columns(),
            sa.Column(
                "article_id", sa.Uuid(), sa.ForeignKey("kb_articles.id"), nullable=False
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
                "article_id",
                "ticket_id",
                name="uq_kb_article_incident_links_article_ticket",
            ),
        )
        op.create_index(
            "ix_kb_article_incident_links_article_id",
            "kb_article_incident_links",
            ["article_id"],
        )
        op.create_index(
            "ix_kb_article_incident_links_ticket_id",
            "kb_article_incident_links",
            ["ticket_id"],
        )
        op.create_index(
            "ix_kb_article_incident_links_is_deleted",
            "kb_article_incident_links",
            ["is_deleted"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # Drop children before parents.
    for table in (
        "kb_article_incident_links",
        "kb_article_versions",
        "kb_articles",
        "kb_categories",
        "kb_article_status_transitions",
        "kb_article_statuses",
    ):
        if table in tables:
            op.drop_table(table)
