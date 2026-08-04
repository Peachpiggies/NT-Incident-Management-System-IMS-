# Domain Model and ER Diagram

## Core Entities

The Phase 1.5 design captures the following primary entities:

- `User`
- `Category`
- `Ticket`
- `TicketComment`
- `Attachment`
- `Notification`
- `AuditEvent`

## Current implementation entities

The repository currently includes these database models:

- `users`
- `categories`
- `tickets`
- `ticket_comments`
- `attachments`
- `notifications`
- `audit_events`

## Entity relationship diagram

```mermaid
erDiagram
    USERS {
        int id PK
        string email
        string full_name
        string password_hash
        string role
        bool is_active
        datetime created_at
        datetime updated_at
    }

    CATEGORIES {
        int id PK
        string name
        text description
        bool is_active
        datetime created_at
        datetime updated_at
    }

    TICKETS {
        int id PK
        string title
        text description
        string priority
        string status
        string affected_asset_service
        int customer_id FK
        int category_id FK
        int assignee_id FK
        datetime escalated_at
        datetime resolved_at
        datetime created_at
        datetime updated_at
    }

    TICKET_COMMENTS {
        int id PK
        int ticket_id FK
        int author_id FK
        text body
        bool is_internal
        datetime created_at
        datetime updated_at
    }

    ATTACHMENTS {
        int id PK
        int ticket_id FK
        int uploader_id FK
        string file_name
        string content_type
        int size_bytes
        string object_key
        bool is_internal
        datetime created_at
        datetime updated_at
    }

    NOTIFICATIONS {
        int id PK
        int user_id FK
        int ticket_id FK
        string message
        datetime read_at
        datetime created_at
        datetime updated_at
    }

    AUDIT_EVENTS {
        int id PK
        int ticket_id FK
        int actor_id FK
        string action
        text detail
        datetime created_at
        datetime updated_at
    }

    USERS ||--o{ TICKETS : "creates"
    USERS ||--o{ TICKETS : "assigned_to"
    USERS ||--o{ TICKET_COMMENTS : "authors"
    USERS ||--o{ ATTACHMENTS : "uploads"
    USERS ||--o{ NOTIFICATIONS : "receives"
    USERS ||--o{ AUDIT_EVENTS : "acts"
    CATEGORIES ||--o{ TICKETS : "categorizes"
    TICKETS ||--o{ TICKET_COMMENTS : "has"
    TICKETS ||--o{ ATTACHMENTS : "has"
    TICKETS ||--o{ NOTIFICATIONS : "has"
    TICKETS ||--o{ AUDIT_EVENTS : "has"
```

## Entity descriptions

### User

Fields:
- `id`
- `email`
- `full_name`
- `password_hash`
- `role`
- `is_active`
- `created_at`
- `updated_at`

### Ticket

Fields:
- `id`
- `title`
- `description`
- `priority`
- `status`
- `affected_asset_service`
- `customer_id`
- `category_id`
- `assignee_id`
- `escalated_at`
- `resolved_at`
- `created_at`
- `updated_at`

### Category

Fields:
- `id`
- `name`
- `description`
- `is_active`
- `created_at`
- `updated_at`

### TicketComment

Fields:
- `id`
- `ticket_id`
- `author_id`
- `body`
- `is_internal`
- `created_at`
- `updated_at`

### Attachment

Fields:
- `id`
- `ticket_id`
- `uploader_id`
- `file_name`
- `content_type`
- `size_bytes`
- `object_key`
- `is_internal`
- `created_at`
- `updated_at`

### Notification

Fields:
- `id`
- `user_id`
- `ticket_id`
- `message`
- `read_at`
- `created_at`
- `updated_at`

### AuditEvent

Fields:
- `id`
- `ticket_id`
- `actor_id`
- `action`
- `detail`
- `created_at`
- `updated_at`

## Naming conventions

- Tables are plural: `users`, `tickets`, `comments`, `attachments`
- Primary keys are `id`
- Foreign keys use snake_case with `_id`
- Timestamps use `created_at`, `updated_at`, and optional `deleted_at`
