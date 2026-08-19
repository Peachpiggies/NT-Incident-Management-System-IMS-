"""Close remaining schema drift between app/db/models.py and the live DB.

0001_initial_schema created the schema via `Base.metadata.create_all()`
using whatever models.py looked like at the time it first ran against a
given database -- it is not a fixed DDL script. Every column/table added
to models.py afterward without an explicit migration silently never
reaches a database that was already provisioned before that change.
0018 closed two such gaps (tickets.resolution_summary/resolution_code);
this migration closes the rest, found via a live-vs-model schema diff
(scripts/check_schema_drift.py):

  - tickets.reopen_count                          (int, default 0)
  - ticket_attachments.scan_status/scanned_at/scan_detail (AV scan state)
  - ticket_comment_mentions                        (whole table missing)

Each step is guarded so this is safe to run against a database that may
already have some (but not all) of these, matching the idempotent style
used in 0012_knowledge_base.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_attachment_mentions_fix"
down_revision = "0018_ticket_resolution_fields"
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


def _columns(bind, table_name: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table_name)}


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # ---------------------------------------------------------------- #
    # tickets.reopen_count
    # ---------------------------------------------------------------- #
    if "reopen_count" not in _columns(bind, "tickets"):
        op.add_column(
            "tickets",
            sa.Column(
                "reopen_count", sa.Integer(), nullable=False, server_default="0"
            ),
        )

    # ---------------------------------------------------------------- #
    # ticket_attachments: AV scan tracking columns
    # ---------------------------------------------------------------- #
    attachment_cols = _columns(bind, "ticket_attachments")
    if "scan_status" not in attachment_cols:
        op.add_column(
            "ticket_attachments",
            sa.Column(
                "scan_status",
                sa.String(length=20),
                nullable=False,
                server_default="PENDING",
            ),
        )
        op.create_index(
            "ix_ticket_attachments_scan_status",
            "ticket_attachments",
            ["scan_status"],
        )
    if "scanned_at" not in attachment_cols:
        op.add_column(
            "ticket_attachments",
            sa.Column("scanned_at", sa.DateTime(timezone=True)),
        )
    if "scan_detail" not in attachment_cols:
        op.add_column(
            "ticket_attachments", sa.Column("scan_detail", sa.Text())
        )

    # ---------------------------------------------------------------- #
    # ticket_comment_mentions (whole table)
    # ---------------------------------------------------------------- #
    if "ticket_comment_mentions" not in tables:
        op.create_table(
            "ticket_comment_mentions",
            *_audit_columns(),
            sa.Column(
                "comment_id",
                sa.Uuid(),
                sa.ForeignKey("ticket_comments.id"),
                nullable=False,
            ),
            sa.Column(
                "user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.UniqueConstraint(
                "comment_id", "user_id", name="uq_ticket_comment_mentions_comment_user"
            ),
        )
        op.create_index(
            "ix_ticket_comment_mentions_comment_id",
            "ticket_comment_mentions",
            ["comment_id"],
        )
        op.create_index(
            "ix_ticket_comment_mentions_user_id",
            "ticket_comment_mentions",
            ["user_id"],
        )
        op.create_index(
            "ix_ticket_comment_mentions_is_deleted",
            "ticket_comment_mentions",
            ["is_deleted"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "ticket_comment_mentions" in tables:
        op.drop_table("ticket_comment_mentions")

    attachment_cols = _columns(bind, "ticket_attachments")
    if "scan_detail" in attachment_cols:
        op.drop_column("ticket_attachments", "scan_detail")
    if "scanned_at" in attachment_cols:
        op.drop_column("ticket_attachments", "scanned_at")
    if "scan_status" in attachment_cols:
        op.drop_index(
            "ix_ticket_attachments_scan_status", table_name="ticket_attachments"
        )
        op.drop_column("ticket_attachments", "scan_status")

    if "reopen_count" in _columns(bind, "tickets"):
        op.drop_column("tickets", "reopen_count")
