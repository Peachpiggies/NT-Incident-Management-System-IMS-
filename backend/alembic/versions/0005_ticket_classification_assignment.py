"""Add subcategory/service classification and assignment query support.

Revision ID: 0005_ticket_classification
Revises: 0004_ticket_query_performance
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_ticket_classification"
down_revision = "0004_ticket_query_performance"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "ticket_subcategories" not in tables:
        op.create_table(
            "ticket_subcategories",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("deleted_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("category_id", sa.Uuid(), sa.ForeignKey("ticket_categories.id"), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("category_id", "code", name="uq_ticket_subcategories_category_code"),
        )
        op.create_index("ix_ticket_subcategories_category_id", "ticket_subcategories", ["category_id"])
        op.create_index("ix_ticket_subcategories_is_deleted", "ticket_subcategories", ["is_deleted"])
    if "ticket_services" not in tables:
        op.create_table(
            "ticket_services",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("deleted_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("subcategory_id", sa.Uuid(), sa.ForeignKey("ticket_subcategories.id"), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("subcategory_id", "code", name="uq_ticket_services_subcategory_code"),
        )
        op.create_index("ix_ticket_services_subcategory_id", "ticket_services", ["subcategory_id"])
        op.create_index("ix_ticket_services_is_deleted", "ticket_services", ["is_deleted"])

    ticket_columns = _columns(bind, "tickets")
    if "subcategory_id" not in ticket_columns:
        op.add_column("tickets", sa.Column("subcategory_id", sa.Uuid(), nullable=True))
        op.create_foreign_key("fk_tickets_subcategory_id_ticket_subcategories", "tickets", "ticket_subcategories", ["subcategory_id"], ["id"])
        op.create_index("ix_tickets_subcategory_id", "tickets", ["subcategory_id"])
    if "service_id" not in ticket_columns:
        op.add_column("tickets", sa.Column("service_id", sa.Uuid(), nullable=True))
        op.create_foreign_key("fk_tickets_service_id_ticket_services", "tickets", "ticket_services", ["service_id"], ["id"])
        op.create_index("ix_tickets_service_id", "tickets", ["service_id"])
    if "ix_tickets_department_status_created" not in _indexes(bind, "tickets"):
        op.create_index("ix_tickets_department_status_created", "tickets", ["department_id", "status_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = _indexes(bind, "tickets")
    if "ix_tickets_department_status_created" in indexes:
        op.drop_index("ix_tickets_department_status_created", table_name="tickets")
    columns = _columns(bind, "tickets")
    if "service_id" in columns:
        op.drop_constraint("fk_tickets_service_id_ticket_services", "tickets", type_="foreignkey")
        op.drop_index("ix_tickets_service_id", table_name="tickets")
        op.drop_column("tickets", "service_id")
    if "subcategory_id" in columns:
        op.drop_constraint("fk_tickets_subcategory_id_ticket_subcategories", "tickets", type_="foreignkey")
        op.drop_index("ix_tickets_subcategory_id", table_name="tickets")
        op.drop_column("tickets", "subcategory_id")
    tables = set(sa.inspect(bind).get_table_names())
    if "ticket_services" in tables:
        op.drop_table("ticket_services")
    if "ticket_subcategories" in tables:
        op.drop_table("ticket_subcategories")