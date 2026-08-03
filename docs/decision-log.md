# Architecture Decision Records (ADR)

This document captures the major architecture and design decisions for the NT Incident Management System.

## ADR 001 — Backend framework

- Decision: Use FastAPI for the backend service.
- Context: FastAPI supports async request handling, automatic OpenAPI generation, and a simple dependency injection model.
- Consequences: Faster implementation of HTTP APIs and easier API documentation for frontend integration.

## ADR 002 — Database

- Decision: Use PostgreSQL for persistent ticket and audit data.
- Context: PostgreSQL is reliable for relational data, strong transaction support, and works well with SQLAlchemy.
- Consequences: A consistent data model and support for future analytics.

## ADR 003 — Authentication

- Decision: Use JWT-based authentication for stateless API access.
- Context: The system is API-first and must support browser clients with token-based auth.
- Consequences: Simpler session handling, but requires careful token security and expiration management.

## ADR 004 — Ticket lifecycle

- Decision: Model ticket status as a state machine.
- Context: Ticket workflow rules should be enforced consistently and not depend only on UI state.
- Consequences: Clear status transitions, simpler business logic, and fewer unexpected state combinations.

## ADR 005 — Error response format

- Decision: Standardize API responses with a uniform success/error payload.
- Context: Frontend and backend need a consistent contract for success and failure handling.
- Consequences: Easier client-side error handling and better API predictability.

## ADR 006 — Deployment

- Decision: Use Docker Compose for local development and as the initial deployment pattern.
- Context: The team needs a reproducible local stack with backend, database, and frontend.
- Consequences: Simplified onboarding, with the ability to move to Kubernetes or managed containers later.
