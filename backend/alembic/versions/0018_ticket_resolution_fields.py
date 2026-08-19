"""Add tickets.resolution_summary / tickets.resolution_code.

The Ticket ORM model (app/db/models.py) has declared these two columns
for a while -- resolution_summary is required input on the /resolve
endpoint -- but no earlier migration ever actually created them in
Postgres. Any query that selects every column off `tickets` (e.g. the
dashboard/analytics service, which does `select(Ticket)` with no
`.options(load_only(...))`) fails with UndefinedColumnError until this
runs. Both are nullable at the DB layer since existing rows predate the
field and the requirement is enforced in the API layer instead.
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_ticket_resolution_fields"
down_revision = "0017_dashboard_analytics_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("tickets")}
    if "resolution_summary" not in cols:
        op.add_column("tickets", sa.Column("resolution_summary", sa.Text(), nullable=True))
    if "resolution_code" not in cols:
        op.add_column("tickets", sa.Column("resolution_code", sa.String(length=50), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("tickets")}
    if "resolution_code" in cols:
        op.drop_column("tickets", "resolution_code")
    if "resolution_summary" in cols:
        op.drop_column("tickets", "resolution_summary")
