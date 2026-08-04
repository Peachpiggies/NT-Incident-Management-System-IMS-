# Phase 1.5 — Software Architecture & System Design

## Goal

Before writing backend features, Phase 1.5 creates a system-level blueprint that aligns implementation, reduces rework, and supports production-quality growth.

When Phase 1.5 is complete, the team will have:

- A clear Software Requirements Specification (SRS)
- A defined domain model and entity boundaries
- A ticket state machine for status transitions
- A role and permission matrix for RBAC
- A REST API contract for backend and frontend teams
- A backend/frontend folder layout aligned to Clean Architecture
- Database naming and conventions
- A consistent API error response standard
- Project-wide coding conventions
- Documentation templates and architecture decision records

## Document map

- `docs/srs.md`
- `docs/architecture.md`
- `docs/api-spec.md`
- `docs/er-diagram.md`
- `docs/permissions.md`
- `docs/ticket-lifecycle.md`
- `docs/migration-design.md`
- `docs/CODING_STANDARDS.md`
- `docs/deployment.md`
- `docs/decision-log.md`
- `docs/risk-register.md`

## Current repository alignment

This repository already has an initial production-oriented foundation:

- Backend: FastAPI + async SQLAlchemy + Alembic
- Frontend: Next.js + TypeScript
- Orchestration: Docker Compose
- Health checks: `/api/v1/healthz` and `/api/v1/readyz`

Phase 1.5 documentation now includes:

- architecture decisions and system layering
- an API contract for implemented and planned endpoints
- an ER diagram for the current domain model
- a ticket lifecycle state machine aligned to backend state transitions
- a permissions matrix tied to role-based actions
- coding standards, deployment guidance, decision logs, and risk register items

Phase 1.5 is now complete for the architecture and documentation deliverables needed to guide Phase 2 implementation.
