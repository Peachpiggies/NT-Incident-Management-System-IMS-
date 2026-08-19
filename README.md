# NT-IMS — Incident Management System

![CI](../../actions/workflows/ci.yml/badge.svg)

A full-stack incident management system: ticketing with SLA tracking and escalation, a knowledge base, notifications, root cause analysis, and problem/change management, built on a Next.js frontend, a FastAPI backend, and PostgreSQL, orchestrated locally with Docker Compose.

## Stack

- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, SQLAlchemy async, Alembic
- Database: PostgreSQL 17
- Local orchestration: Docker Compose

## Quick start

Requirements: Docker Engine with Compose v2. Node.js 20+ is only needed when running the frontend outside Docker; Python 3.11+ is only needed for local backend development.

```bash
cp .env.example .env
docker compose up --build
```

Open the frontend at <http://localhost:3000>, API documentation at <http://localhost:8002/docs>, and the health endpoints below. The home page displays the live database-readiness result rather than a cached liveness response.

## API contract

The API contract is available as OpenAPI at `/api/v1/openapi.json` and Swagger UI at `/docs`.
All resource IDs are UUIDs. Protected operations use permission-based access control
(for example `ticket.assign`, `role.manage`, and `department.manage`); ticket reads
also enforce `ticket.read_own` or `ticket.read_all`. Log in with
`POST /api/v1/auth/login` and send the access token as a Bearer token.

Session endpoints are available at `/api/v1/auth/sessions`. They return device/IP
metadata but never expose refresh-token hashes or JWT IDs.

Stop the stack with `docker compose down`. To remove the development database as well, run `docker compose down --volumes`.

## Local development

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

Backend:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

For local backend execution, set `DATABASE_URL` in `backend/.env` to a reachable PostgreSQL instance (for example, `localhost` when the database is started by Compose).

## Database migrations

Database migrations are managed by Alembic from the `backend/` folder. See `docs/migration-design.md` for the migration strategy, required environment variables, and maintenance notes.

Create a revision after adding or changing ORM models, then apply it to the local database:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://ims:change-me-for-local-development@db:5432/ims \
JWT_SECRET=secret \
python -m alembic -c alembic.ini revision --autogenerate -m "describe_change"
python -m alembic -c alembic.ini upgrade head
```

## Environment configuration

Copy `.env.example` to `.env`; the two files use the same development defaults. The root `.env` is consumed by Docker Compose and contains the backend connection string using the Compose hostname `db`. Never commit `.env` or production credentials. `NEXT_PUBLIC_*` values are exposed to the browser and must never contain secrets.

When running the frontend outside Docker, copy `frontend/.env.example` to `frontend/.env.local`. When running the backend outside Docker, create `backend/.env` from the root template and change only `DATABASE_URL` to use a reachable PostgreSQL host such as `localhost`.

## Health checks

- `GET /api/v1/healthz` is the liveness check; it only confirms that the API process is running.
- `GET /api/v1/readyz` is the database-ready check; it executes `SELECT 1` against PostgreSQL and returns `{"status":"ok","database":"connected"}` only when the database is reachable.

Docker Compose uses `/readyz` for the backend health check, so the frontend starts only after the API and database are ready.

## Repository layout

```text
.
├── backend/             # FastAPI application and database migration tooling
│   ├── alembic/         # Migrations
│   ├── scripts/         # Maintenance/diagnostic scripts (e.g. schema drift check)
│   ├── tests/           # Pytest suite
│   └── app/
│       ├── api/         # Versioned HTTP routes
│       ├── core/        # Configuration and cross-cutting concerns
│       ├── db/          # Engine, sessions, ORM base
│       ├── schemas/     # Pydantic request/response models
│       └── services/    # Business logic (SLA, workflow, notifications, etc.)
├── frontend/            # Next.js application
│   └── app/             # App Router routes and UI
├── docs/                # Engineering documentation
├── scripts/             # Ops scripts (db backup/restore)
├── docker-compose.yml   # Full local development stack
└── .env.example         # Safe configuration template
```

## Quality checks

```bash
cd frontend && npm run lint && npm run typecheck
cd ../backend && python -m ruff check app tests && python -m pytest tests
```

See [coding standards](docs/CODING_STANDARDS.md) and [contribution guide](CONTRIBUTING.md) before opening a pull request.