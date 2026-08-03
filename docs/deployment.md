# Deployment

## Local development

Use Docker Compose for the integrated stack:

```bash
cp .env.example .env
docker compose up --build
```

Frontend: `http://localhost:3000`
Backend docs: `http://localhost:8002/docs`

## Health checks

- `GET /api/v1/healthz` — process liveness
- `GET /api/v1/readyz` — database readiness

## Production considerations

- Use HTTPS behind a load balancer or reverse proxy.
- Use environment-specific values for `DATABASE_URL`, `JWT_SECRET`, and S3 credentials.
- Configure container restarts and health checks in orchestration.
