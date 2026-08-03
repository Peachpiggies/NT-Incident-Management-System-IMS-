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

## Commit and branch conventions

- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Branch names should be descriptive and follow `feature/<short-description>`, `fix/<short-description>`, or `docs/<short-description>`.

## File naming

- Use lowercase, dash-separated file names for frontend files and snake_case for Python files.
- Use descriptive names for routers, schemas, services, and components.

## API naming

- Use RESTful routes under `/api/v1`.
- Use nouns for resources, verbs for actions only when necessary.
- Keep payloads consistent across endpoints.

## DTO / schema naming

- Use `CreateUserRequest`, `UpdateTicketRequest`, `TicketResponse`.
- Keep request and response models separate.

## Environment variables

- Use `.env.example` to document required runtime settings.
- Prefix browser-exposed vars with `NEXT_PUBLIC_`.

## Backend best practices

- Keep route handlers thin and delegate business logic to services.
- Use dependency injection for database sessions and current user retrieval.
- Use typed Pydantic models for request validation and response serialization.

## Frontend best practices

- Keep UI components reusable and presentation-focused.
- Keep data-fetching logic in `services/` or `hooks/`.
- Prefer composable hooks and typed response models.

## Testing

- Add tests for API contracts, domain services, and critical logic.
- Validate state transitions and permission rules with automated tests.
