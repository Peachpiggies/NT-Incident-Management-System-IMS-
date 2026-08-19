"""One-off diagnostic: compares the live Postgres schema against what the
SQLAlchemy models (app/db/models.py) declare, table by table and column by
column. Read-only -- makes no changes.
"""

import asyncio

from sqlalchemy import inspect

from app.db.models import Base
from app.db.session import engine


async def main() -> None:
    async with engine.connect() as conn:
        def _inspect(sync_conn):
            insp = inspect(sync_conn)
            return {
                table_name: {col["name"] for col in insp.get_columns(table_name)}
                for table_name in insp.get_table_names()
            }

        live_schema = await conn.run_sync(_inspect)

    any_drift = False
    for table in Base.metadata.sorted_tables:
        model_cols = {c.name for c in table.columns}
        if table.name not in live_schema:
            print(f"[MISSING TABLE] {table.name}")
            any_drift = True
            continue
        db_cols = live_schema[table.name]
        missing_in_db = sorted(model_cols - db_cols)
        extra_in_db = sorted(db_cols - model_cols)
        if missing_in_db:
            any_drift = True
            print(f"[{table.name}] missing in DB: {missing_in_db}")
        if extra_in_db:
            print(f"[{table.name}] extra in DB (not in model, informational only): {extra_in_db}")

    if not any_drift:
        print("No drift found — DB matches models.")


if __name__ == "__main__":
    asyncio.run(main())
