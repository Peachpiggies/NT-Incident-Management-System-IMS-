# Phase 2 — Database Design & Authentication

## Goal

> Build a real login system and a database foundation that supports future expansion.

Phase 2 is the critical phase for this project. A well-designed database and authorization model here makes later phases much easier.

## Sprint 2.1 Requirement Analysis

Before writing the database, answer these questions.

### User roles

- Who is a Customer?
- Who is Tier 1?
- Who is Tier 2?
- Who is a Manager?

Each role should be defined by what they can do.

### Ticket

Ticket fields should include:

- Ticket Number
- Title
- Description
- Priority
- Category
- Status
- Reporter
- Assignee
- Department
- Created At
- Updated At
- Resolved At
- Closed At

### Attachment

- How many files can be attached?
- Supported file types:
  - JPG
  - PNG
  - PDF
  - DOCX
- Maximum file size

### Comment

Support:

- Public comment
- Internal note
- Mention users

### Notification

Notification channels:

- Email
- Browser notification
- LINE

## Sprint 2.2 Database Design

Design the ER diagram.

Expected tables:

- `roles`
- `users`
- `departments`
- `ticket_categories`
- `ticket_priorities`
- `ticket_statuses`
- `tickets`
- `ticket_assignments`
- `ticket_comments`
- `ticket_attachments`
- `ticket_histories`
- `notifications`
- `refresh_tokens`
- `audit_logs`

Around 12–15 tables in total.

## Sprint 2.3 Database Normalization

Validate:

- ✅ 1NF
- ✅ 2NF
- ✅ 3NF

This prevents:

- duplicated data
- inconsistent data
- update anomalies

## Sprint 2.4 SQLAlchemy Models

Create models for:

- `BaseModel`
- `User`
- `Role`
- `Ticket`
- `Comment`
- `Attachment`
- `Notification`
- etc.

Each model should include:

- `relationship()`
- foreign keys
- indexes
- constraints

## Sprint 2.5 Alembic

Database migration workflow:

- `alembic init`
- `alembic revision`
- `alembic upgrade`
- `alembic downgrade`

After this sprint, the database should be reproducible from a single command.

## Sprint 2.6 Authentication

Build full authentication flows:

- Login
- Logout
- Register
- Refresh token
- Change password
- Forgot password (future)

## Sprint 2.7 Authorization

Implement RBAC by role.

### Customer

- Create ticket
- Read own ticket
- Comment own ticket

### Tier1

- View queue
- Assign ticket
- Resolve ticket
- Escalate

### Tier2

- Receive escalated ticket
- Resolve ticket
- Add internal notes

### Manager

- Dashboard
- Reports
- Manage users
- Manage roles
- View all tickets

## Sprint 2.8 JWT

Use JWT for session management:

- Access token
- Refresh token
- Password hash
- bcrypt
- JWT expiration
- Token rotation

## Sprint 2.9 Validation

Use Pydantic models for request validation:

- `UserCreate`
- `UserLogin`
- `TicketCreate`
- `TicketUpdate`
- `CommentCreate`

Validate:

- Email
- Password
- Phone
- File uploads

## Sprint 2.10 API

Add authentication and identity endpoints:

- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/refresh`
- `GET /users/me`
- `GET /roles`
- `GET /permissions`

## Sprint 2.11 Seed Data

Create initial seed records for:

- Roles: Admin, Manager, Tier1, Tier2, Customer
- Admin account
- Departments
- Priorities
- Statuses
- Categories

## Sprint 2.12 Testing

Add unit tests for:

- Login
- JWT
- Permission checks
- Create user
- Password hashing

## Deliverables

When Phase 2 is complete, the system should have:

- ✅ Database ready to use
- ✅ Migration support
- ✅ Login
- ✅ JWT
- ✅ Refresh token
- ✅ RBAC
- ✅ Swagger documentation
- ✅ Seed data
- ✅ SQLAlchemy models
- ✅ Authentication API

## Production-grade additions

To make this project stand out as enterprise-ready, add these items in Phase 2.

### 1. UUID instead of auto-increment

- Use UUID primary keys on all tables.
- Reduce guessable IDs and support distributed systems later.

### 2. Soft delete

Use soft deletion instead of hard delete:

- `deleted_at TIMESTAMP`
- `deleted_by UUID`

This supports audit and recovery.

### 3. Audit columns on every table

Standard audit fields for all tables:

- `created_at`
- `updated_at`
- `created_by`
- `updated_by`
- `deleted_at`
- `deleted_by`

### 4. Enum tables + business configuration

Avoid hard-coded priority/status values.

Example tables:

- `Priority` — Low, Medium, High, Critical
- `Status` — New, Assigned, In Progress, Pending, Resolved, Closed

This allows admins to change business configuration without code changes.

### 5. Permission-based access control (PBAC)

Build a structure that can evolve beyond RBAC:

- `Role`
- `Permission`
- `Action`
- `Resource`

Example permissions:

- `ticket:create`
- `ticket:update`
- `ticket:delete`
- `user:manage`
- `report:view`

### 6. Audit log

Record important actions such as:

- who logged in
- who created a ticket
- who changed a ticket status
- who assigned a ticket
- who edited data

This improves security and traceability.

## Current repository alignment

The existing backend already provides a good foundation for Phase 2:

- FastAPI backend
- async SQLAlchemy models
- JWT helper functions in `app/core/security.py`
- database configuration in `app/core/config.py`

Phase 2 should extend this foundation into a full authentication and authorization system with a normalized database schema.
