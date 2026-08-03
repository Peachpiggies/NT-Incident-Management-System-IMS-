# Coding standards

## Shared

- Use English for code, API contracts, commit messages, and technical documentation.
- Keep pull requests focused; include tests or a short verification note.
- Use Conventional Commits: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, or `chore`.
- Do not commit secrets, generated build output, or local database files.

## Frontend

- Use TypeScript; avoid `any` and type public component props.
- Keep routes in `app/`; place reusable UI and client utilities in purpose-specific folders as they are introduced.
- Run `npm run lint` and `npm run typecheck` before review.

## Backend

- Use type hints for public functions and Pydantic models for request/response schemas.
- Keep route handlers thin; add domain services and repositories when business logic is introduced.
- Use async SQLAlchemy sessions via the supplied `get_db` dependency.
- Format with Black and lint with Ruff.
