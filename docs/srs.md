# Software Requirements Specification (SRS)

## Project scope

The system is an incident and ticket management platform for customer support, escalation, and reporting.

### Primary users

- Customer
- Tier 1 support
- Tier 2 support
- Manager

## Functional requirements

### Customer

- Register and log in
- Create a ticket with category, priority, and description
- Upload attachments to a ticket
- View own tickets
- Add comments to own tickets
- Close completed tickets

### Tier 1 support

- View assigned tickets and queue
- Assign tickets to self or escalate to Tier 2
- Change ticket status
- Reply to customers
- Add internal notes

### Tier 2 support

- View escalated tickets
- Investigate technical issues
- Resolve tickets
- Add internal notes
- Collaborate with Tier 1 and manager

### Manager

- View dashboards and analytics
- Generate reports
- Manage users and roles
- Manage categories and priorities
- Monitor service metrics and SLA status

## Non-functional requirements

### Performance

- API response time under 300 ms for normal requests
- Support 100–500 concurrent users in the first phase

### Security

- JWT-based authentication
- HTTPS for production
- Secure password hashing
- Role-based access control (RBAC)

### Availability

- Deployable via Docker Compose
- Health checks for service readiness and liveness

### Maintainability

- Use Clean Architecture and layered services
- Follow SOLID principles where practical
- Use repository/service patterns for data access and business logic
- Keep route handlers thin

## Constraints and assumptions

- The first phase targets internal or limited production use
- Attachments may be stored in S3-compatible storage
- The frontend and backend should evolve independently through the API contract
- Existing backend implementation uses PostgreSQL and async SQLAlchemy
