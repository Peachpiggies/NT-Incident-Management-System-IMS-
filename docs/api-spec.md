# API Specification

## API base path

All endpoints are versioned under `/api/v1`.

## Common response format

This API follows a standard success/error envelope for frontend consistency.

#### Success

```json
{
  "success": true,
  "data": {
    "id": 123,
    "title": "Example"
  },
  "message": "Request completed successfully"
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
- Response: access token + refresh token
- Permission: public

### POST /api/v1/auth/login

- Request: `email`, `password`
- Response: access token + refresh token
- Permission: public

### POST /api/v1/auth/refresh

- Request: `refresh_token`
- Response: new access token + refresh token
- Permission: public

### POST /api/v1/auth/logout

- Request: `refresh_token`
- Response: `204 No Content`
- Permission: authenticated via refresh token

## Users

### GET /api/v1/users/me

- Response: current authenticated user profile
- Permission: authenticated

### GET /api/v1/roles

- Response: list of available role names
- Permission: public

## Permissions

### GET /api/v1/permissions

- Response: permission matrix by role
- Permission: public

## Tickets

### POST /api/v1/tickets

- Create a ticket
- Request schema: `title`, `description`, `category_id`, `priority`, `affected_asset_service`
- Response: created ticket model
- Permission: customer

### GET /api/v1/tickets

- List tickets
- Customer: own tickets only
- Tier 1 / Tier 2 / Manager: all tickets
- Permission: authenticated

### GET /api/v1/tickets/{ticket_id}

- Response: ticket details
- Permission:
  - Customer may read own ticket
  - Support may read by role and workflow

### GET /api/v1/tickets/{ticket_id}/comments

- Response: ticket comments
- Customers see only public comments
- Support users also see internal notes
- Permission: authenticated

### POST /api/v1/tickets/{ticket_id}/comments

- Create a public ticket comment
- Request schema: `body`
- Permission: customer on own ticket

### POST /api/v1/tickets/{ticket_id}/assign

- Assign a ticket
- Request schema: `assignee_id` optional
- Permission: Tier 1 or Manager

### POST /api/v1/tickets/{ticket_id}/escalate

- Escalate a ticket to Tier 2
- Permission: Tier 1

### POST /api/v1/tickets/{ticket_id}/receive_escalated

- Accept an escalated ticket into Tier 2 workflow
- Permission: Tier 2

### POST /api/v1/tickets/{ticket_id}/resolve

- Resolve a ticket
- Permission: Tier 1 or Tier 2

### POST /api/v1/tickets/{ticket_id}/close

- Close a resolved ticket
- Permission: Tier 1, Tier 2, or Manager

### POST /api/v1/tickets/{ticket_id}/reopen

- Reopen a resolved or closed ticket
- Permission: Tier 1, Tier 2, or Manager

### POST /api/v1/tickets/{ticket_id}/internal-note

- Create an internal note visible only to support staff
- Request schema: `body`
- Permission: Tier 2

## Categories (planned)

### GET /api/v1/categories

- List active categories
- Permission: authenticated

### POST /api/v1/categories

- Create a category
- Permission: manager

### PATCH /api/v1/categories/{category_id}

- Update category details
- Permission: manager

## Dashboard and reports (planned)

### GET /api/v1/dashboard/summary

- Counts by status, escalated tickets, SLA breach measures
- Permission: manager

### GET /api/v1/dashboard/queue

- Assigned/unassigned ticket queue view
- Permission: Tier 1, Tier 2, manager

### GET /api/v1/reports/tickets

- Paginated ticket report
- Permission: manager

### GET /api/v1/reports/users

- Support performance summary
- Permission: manager

## Health

### GET /api/v1/healthz

- Liveness check
- Permission: public

### GET /api/v1/readyz

- Database readiness check
- Permission: public
