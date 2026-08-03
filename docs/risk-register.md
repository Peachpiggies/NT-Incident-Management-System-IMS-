# Risk Register

## Risk 001 — Large file uploads

- Description: Attachments may be large and could exceed storage or upload limits.
- Impact: High
- Likelihood: Medium
- Mitigation:
  - Enforce maximum file size in API and frontend.
  - Use S3-compatible storage with signed upload links.
  - Validate content types and scan for malware if needed.

## Risk 002 — Concurrent ticket updates

- Description: Multiple support agents may update the same ticket simultaneously.
- Impact: Medium
- Likelihood: Medium
- Mitigation:
  - Use optimistic locking or explicit version fields.
  - Validate state transitions in business logic.
  - Return clear conflict responses for stale updates.

## Risk 003 — Role and permission drift

- Description: Access rules may become inconsistent as features grow.
- Impact: High
- Likelihood: Medium
- Mitigation:
  - Centralize permission checks in middleware or service helpers.
  - Keep the role permission matrix documented and updated.
  - Add automated tests for permission rules.

## Risk 004 — Performance under load

- Description: API response time may degrade when the system supports many concurrent users.
- Impact: Medium
- Likelihood: Medium
- Mitigation:
  - Add request pagination and indexes for common queries.
  - Monitor response times and slow queries.
  - Use connection pooling and async database sessions.

## Risk 005 — Sensitive data exposure

- Description: JWT secrets, database credentials, or file URLs may leak in logs or config.
- Impact: High
- Likelihood: Medium
- Mitigation:
  - Store secrets in environment variables, not source control.
  - Do not log sensitive data.
  - Use HTTPS in production and rotate credentials when necessary.
