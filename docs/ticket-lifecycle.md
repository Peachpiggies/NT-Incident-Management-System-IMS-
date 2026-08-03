# Ticket Lifecycle

## State machine

The ticket lifecycle is modeled as a finite state machine rather than free-text status values.

### States

- `NEW`
- `ASSIGNED`
- `IN_PROGRESS`
- `PENDING`
- `RESOLVED`
- `CLOSED`
- `REOPENED`

### Allowed transitions

```text
NEW
 │
 ▼
ASSIGNED
 │
 ▼
IN_PROGRESS
 │
 ├──────────────┐
 ▼              │
PENDING         │
 │              │
 ▼              │
RESOLVED────────┘
 │
 ▼
CLOSED
```

From `CLOSED`, a ticket may transition to:

```text
CLOSED -> REOPENED -> ASSIGNED
```

## Notes

- The implementation in `app/domain.py` currently uses `TicketStatus.OPEN` as the initial state.
- Phase 1.5 should align the domain enum to the state machine and introduce transition validation in the service layer.
- The state machine should be enforced in business logic, not only by UI choices.
