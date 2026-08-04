"""Production-grade UUID, audit and RBAC foundation.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-04
"""

from alembic import op

from app.db.models import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLAlchemy owns the schema definition.  This initial revision deliberately
    # contains no hard-coded PostgreSQL enum types: all business values are rows
    # in master-data tables and therefore configurable at runtime.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
