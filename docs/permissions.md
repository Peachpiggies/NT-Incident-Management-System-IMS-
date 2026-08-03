# Role & Permission Matrix

## Roles

- Customer
- Tier 1
- Tier 2
- Manager

## Permission matrix

| Action                         | Customer | Tier 1 | Tier 2 | Manager |
|------------------------------|:--------:|:------:|:------:|:-------:|
| Create Ticket                | ✅       | ❌     | ❌     | ❌      |
| View Own Ticket              | ✅       | ✅     | ✅     | ✅      |
| View All Tickets             | ❌       | ✅     | ✅     | ✅      |
| Comment Own Ticket           | ✅       | ✅     | ✅     | ✅      |
| Assign Ticket                | ❌       | ✅     | ❌     | ✅      |
| Escalate                     | ❌       | ✅     | ❌     | ✅      |
| Receive Escalated Ticket     | ❌       | ❌     | ✅     | ✅      |
| Resolve Ticket               | ❌       | ✅     | ✅     | ✅      |
| Add Internal Note            | ❌       | ❌     | ✅     | ✅      |
| Close Ticket                 | ❌       | ✅     | ✅     | ✅      |
| Reopen Ticket                | ❌       | ✅     | ✅     | ✅      |
| Manage Users                 | ❌       | ❌     | ❌     | ✅      |
| Manage Categories            | ❌       | ❌     | ❌     | ✅      |
| View Dashboard               | ❌       | ❌     | ❌     | ✅      |

## Current implementation

The backend implements the following role-based actions:

- Customer: create ticket, read own tickets, add public comments
- Tier 1: list all tickets, assign ticket, escalate ticket, resolve ticket, close/reopen ticket
- Tier 2: receive escalated ticket, resolve ticket, add internal notes, close/reopen ticket
- Manager: view all tickets, assign tickets, resolve tickets, close/reopen tickets, manage users and roles in future phases

## Future extension

The system can evolve from role-based access control (RBAC) to permission-based access control by introducing permission records and policy enforcement middleware.
