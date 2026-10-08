# MATT — Autonomous AI Company Operating System

MATT is a multi-agent orchestration platform, skill registry, business operating system and
command center. The owner sets long-term objectives; MATT's AI workforce researches, builds,
sells and reports, and asks the owner before any action that spends money, contacts people,
touches sensitive data or changes infrastructure.

> MATT does not guarantee any revenue outcome. It tracks facts, and labels estimates,
> predictions and assumptions as such.

## Status

Built incrementally per the [roadmap](docs/roadmap.md). **Phase 1 (foundation) is done.**

| Works today | Not built yet (shown as "Coming soon" in the UI) |
| --- | --- |
| FastAPI backend, PostgreSQL/SQLite, Alembic migrations | Task execution, workflows, tool registry, event bus (Phase 2) |
| Owner bootstrap, JWT auth, RBAC (owner/admin/operator/viewer) | Approval Center, analytics (Phase 3) |
| Agent registry: CEO, 9 executives, 100 skills, 10 self-upgrade skills | Opportunities, leads, website auditing (Phase 4) |
| Lifecycle state machine, owner-only permission changes, versioning | Revenue engines, experiments (Phase 5) |
| Audit log, structured JSON logs with request ids, security headers | Voice (Phase 6), Skill Factory / AI University (Phase 7) |
| Command Center, Workforce Map, Agents, Agent detail, Audit Log pages | Production hardening (Phase 8) |

No agent executes work yet, so the UI shows no agent activity, revenue or customers.

## Quick start (development)

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+.

```bash
# API
cd backend
cp .env.example .env              # defaults use SQLite
uv sync
uv run alembic upgrade head
uv run matt seed-registry         # registers the 120-agent workforce (idempotent)
uv run uvicorn app.main:app --reload

# Web (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:5173, proxies /api to :8000
```

Open http://localhost:5173. On first run you create the owner account (or run
`uv run matt create-owner --email you@example.com`). API docs are at http://localhost:8000/docs.

## Checks

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

CI runs all of these, plus migrations and seeding against PostgreSQL.

## Layout

```text
backend/
  app/
    api/          routes, dependencies (auth, RBAC), middleware
    core/         config, domain vocabulary, security, logging, rate limiting
    db/           engine, session, declarative base
    models/       SQLAlchemy models
    repositories/ query functions
    schemas/      request/response models
    services/     business rules (registry, auth, audit)
    registry/     workforce catalog (data/workforce.yaml) and its loader
  migrations/     Alembic
  tests/
frontend/
  src/api         typed API client
  src/components  layout and shared UI
  src/lib         auth, navigation, formatting
  src/pages       one file per page
docs/             architecture, security, deployment, roadmap
```

## Documentation

- [Architecture](docs/architecture.md)
- [Security](docs/security.md)
- [Deployment and monitoring](docs/deployment.md)
- [Roadmap](docs/roadmap.md)
