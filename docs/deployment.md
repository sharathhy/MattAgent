# Deployment and monitoring

## Configuration

All settings are environment variables prefixed `MATT_` (see `backend/.env.example`).
Production requires `MATT_ENV=production`, a PostgreSQL `MATT_DATABASE_URL`, and a random
`MATT_SECRET_KEY` of at least 32 characters:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Docker Compose

```bash
export POSTGRES_PASSWORD=... MATT_SECRET_KEY=...
docker compose up --build
```

The web app is served on http://localhost:8080; nginx proxies `/api` to the backend. On start the
backend applies migrations (`alembic upgrade head`) and registers any new catalog agents. Create
the owner in the browser or with `docker compose exec backend uv run --no-sync matt create-owner --email you@example.com`.

The stack is free to run on a single small VM. Managed PostgreSQL or a PaaS can replace any
piece; only environment variables change.

## Migrations

- Create: `uv run alembic revision --autogenerate -m "describe change"`, then review the file.
- Apply: `uv run alembic upgrade head`.
- `tests/test_migrations.py` fails if models and migrations drift apart.
- Back up the database before applying migrations in production.

## Backups

Schedule `pg_dump` (e.g. daily, retained 14 days) to storage outside the database host, and
test restores. Phase 8 automates this.

## Monitoring

- **Health:** `GET /api/health` returns 200 with `database: ok`, or 503 when the database is
  unreachable. Point an uptime checker or container health check at it.
- **Logs:** one JSON object per line on stdout, including `request_id`, method, path, status and
  `duration_ms` for every request. Ship stdout to any log store (Loki, CloudWatch, etc.). Every
  response carries `X-Request-ID` for correlation.
- **Audit:** `GET /api/audit-logs` (admin) or the Audit Log page.
- Metrics, tracing and cost tracking arrive with the orchestrator (Phase 2) and hardening
  (Phase 8).
