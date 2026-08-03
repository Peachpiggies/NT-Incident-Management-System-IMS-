# Migration Design

This document describes the database migration strategy and the initial schema migration plan for the NT Incident Management System.

## Goals

- Keep the database schema reproducible and version-controlled.
- Enable safe incremental changes through Alembic revisions.
- Ensure the development and CI environments can apply the same migration history.
- Preserve domain constraints and enum definitions in the database.

## Migration tooling

The backend uses Alembic for migration management and SQLAlchemy models as the schema source.

- Migrations live under `backend/alembic/versions/`
- The Alembic config file is `backend/alembic.ini`
- The SQLAlchemy metadata root is `app/db/session.py` (`Base.metadata`)
- The `env.py` script loads runtime configuration from `app/core/config.py`

## Initial migration

The first migration is `0001_initial_schema.py` and creates the following tables:

- `users`
- `categories`
- `tickets`
- `ticket_comments`
- `attachments`
- `notifications`
- `audit_events`
- `refresh_tokens`

It also creates enum types:

- `role`
- `priority`
- `ticket_status`

## How to create and apply migrations

1. Update SQLAlchemy models in `backend/app/db/models.py`.
2. Run from the backend directory:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://ims:change-me-for-local-development@db:5432/ims \
JWT_SECRET=secret \
/home/peach/.venv/bin/python -m alembic -c alembic.ini revision --autogenerate -m "describe change"
```

3. Apply the migration:

```bash
cd backend
/home/peach/.venv/bin/python -m alembic -c alembic.ini upgrade head
```

4. Validate the schema against the current models.

## Rollback strategy

- Use `alembic downgrade -1` to revert the last revision.
- For larger rollbacks, target a specific revision ID.
- Always review generated SQL before applying to production.

## Deployment considerations

- The app should run migrations as part of deployment startup or release pipeline.
- Ensure production environment variables are set for `DATABASE_URL` and `JWT_SECRET` during migration.
- Use database backups and migration dry-runs for large schema changes.

## Notes

- The current Alembic configuration uses `sqlalchemy.url` in `backend/alembic.ini` only for local convenience; runtime DB connection settings are derived from `app/core/config.py`.
- The repository currently uses a Docker Compose hostname `db` for local database connectivity.
