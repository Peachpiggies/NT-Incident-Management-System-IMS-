# Role & Permission Matrix

## Roles

- Customer
- Tier 1
- Tier 2
- Manager

## Permission matrix

| Action               | Customer | Tier 1 | Tier 2 | Manager |
|----------------------|:--------:|:------:|:------:|:-------:|
| Create Ticket        | ✅       | ❌     | ❌     | ❌      |
| View Own Ticket      | ✅       | ❌     | ❌     | ❌      |
| View All Tickets     | ❌       | ✅     | ✅     | ✅      |
| Assign Ticket        | ❌       | ✅     | ❌     | ✅      |
| Escalate             | ❌       | ✅     | ❌     | ✅      |
| Resolve Ticket       | ❌       | ✅     | ✅     | ✅      |
| Close Ticket         | ✅       | ✅     | ✅     | ✅      |
| Manage Users         | ❌       | ❌     | ❌     | ✅      |
| Manage Categories    | ❌       | ❌     | ❌     | ✅      |
| View Dashboard       | ❌       | ❌     | ❌     | ✅      |

## Future extension

The system can evolve from role-based access control (RBAC) to permission-based access control by introducing permission records and policy enforcement middleware.
