# Architecture Overview

## System architecture

The application is divided into two primary layers:

- Frontend: a Next.js + TypeScript client running in the browser
- Backend: a FastAPI application serving HTTP JSON APIs

Data persistence is handled by PostgreSQL accessed through async SQLAlchemy, with migration tooling provided by Alembic.

### Backend architecture

The backend is organized with a layered structure to separate responsibilities:

- `app/api/` — HTTP routes and versioned API endpoints
- `app/core/` — configuration, security, and shared runtime concerns
- `app/db/` — database engine, session management, and ORM models
- `app/domain.py` — shared enums and domain rules such as ticket status transitions
- `app/main.py` — application composition and middleware

### Frontend architecture

The frontend follows Next.js conventions with app-router pages, reusable UI components, and service abstractions for API calls.

### Folder structure for future phases

```text
backend/
  app/
    api/
      v1/
      dependencies/
    core/
    models/
    schemas/
    repositories/
    services/
    auth/
    database/
    middleware/
    utils/
    tests/

frontend/
  src/
    app/
    features/
    components/
    hooks/
    services/
    lib/
    stores/
    types/
    utils/
```

## Technology choices

- FastAPI: lightweight, async, OpenAPI-ready
- SQLAlchemy Async: modern async ORM for PostgreSQL
- Alembic: database migrations
- PostgreSQL: reliable relational data model for ticketing and auditing
- Next.js: fast frontend, strong type safety, and routing
- Docker Compose: integrated local development stack

## Architecture decisions

Phase 1.5 should capture architectural decisions in `docs/decision-log.md`. Initial decisions include:

- Use FastAPI for backend
- Use PostgreSQL for transactional ticket data
- Use JWT for stateless authentication
- Use a ticket state machine for consistent lifecycle rules
- Use a shared error response format for frontend integration

## Current implementation notes

The current repo already includes:

- `app/domain.py` with role and ticket status enums
- `app/db/models.py` with user, category, ticket, comment, attachment, notification, and audit models
- health endpoints in `app/api/v1/health.py`

Future architecture work should preserve these modules and expand with dedicated repositories, services, and schema layers.
