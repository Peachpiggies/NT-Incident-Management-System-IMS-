# API Specification

## API base path

All endpoints are versioned under `/api/v1`.

### Common response format

#### Success

```json
{
  "success": true,
  "data": {},
  "message": "Ticket created successfully"
}
```

#### Error

```json
{
  "success": false,
  "error": {
    "code": "TICKET_NOT_FOUND",
    "message": "Ticket not found"
  }
}
```

## Authentication

### POST /api/v1/auth/register

- Request: `email`, `full_name`, `password`
- Response: auth token and user details
- Permission: public

### POST /api/v1/auth/login

- Request: `email`, `password`
- Response: access token
- Permission: public

### GET /api/v1/auth/me

- Response: current user profile
- Permission: authenticated

## Users

### GET /api/v1/users

- Response: list of users
- Permission: manager

### GET /api/v1/users/{user_id}

- Response: user details
- Permission: manager or self

### POST /api/v1/users

- Create user (manager only)
- Permission: manager

### PATCH /api/v1/users/{user_id}

- Update user data and role
- Permission: manager or self for profile fields

## Tickets

### POST /api/v1/tickets

- Create a ticket
- Request: `title`, `description`, `category_id`, `priority`, optional attachments
- Permission: customer

### GET /api/v1/tickets

- List tickets
- Permission:
  - Customers see own tickets
  - Tier 1/Tier 2/manager see all tickets

### GET /api/v1/tickets/{ticket_id}

- Response: ticket details, status, comments, attachments
- Permission: owner, assigned support, or manager

### PATCH /api/v1/tickets/{ticket_id}

- Update ticket fields and status transitions
- Request: fields may include `assignee_id`, `status`, `priority`, `category_id`
- Permission: Tier 1, Tier 2, manager as defined by role

### POST /api/v1/tickets/{ticket_id}/comments

- Add a comment
- Request: `body`, `is_internal`
- Permission:
  - Customers may add public comments to own tickets
  - Support can add public or internal comments

### POST /api/v1/tickets/{ticket_id}/attachments

- Upload file attachments
- Permission: ticket owner, assigned staff, or manager

### POST /api/v1/tickets/{ticket_id}/close

- Close a ticket
- Permission: owner, support, manager depending on status

### POST /api/v1/tickets/{ticket_id}/reopen

- Reopen a closed ticket
- Permission: owner or manager

## Categories

### GET /api/v1/categories

- List active categories
- Permission: authenticated

### POST /api/v1/categories

- Create category
- Permission: manager

### PATCH /api/v1/categories/{category_id}

- Update category details
- Permission: manager

## Dashboard

### GET /api/v1/dashboard/summary

- Response: counts by status, escalated tickets, SLA breaches
- Permission: manager

### GET /api/v1/dashboard/queue

- Response: assigned/unassigned ticket queue
- Permission: Tier 1, Tier 2, manager

## Reports

### GET /api/v1/reports/tickets

- Response: paginated ticket report
- Permission: manager

### GET /api/v1/reports/users

- Response: support performance summary
- Permission: manager

## Health

### GET /api/v1/healthz

- Liveness check
- Permission: public

### GET /api/v1/readyz

- Database readiness check
- Permission: public
