# MATT — Autonomous AI Company Operating System

MATT is a multi-agent orchestration platform, skill registry, business operating system and
command center. The owner sets long-term objectives; MATT's AI workforce researches, builds,
sells and reports, and asks the owner before any action that spends money, contacts people,
touches sensitive data or changes infrastructure.

> MATT does not guarantee any revenue outcome. It tracks facts, and labels estimates,
> predictions and assumptions as such.

## Status

Built incrementally per the [roadmap](docs/roadmap.md). Phases 1 and 2 are done, with the
first working pieces of phases 3 to 5.

What works today:

- **Agents that do work.** Any of the 120 registered agents can take an objective. The CEO and
  executives can delegate to their teams. Work runs on a database-backed queue with retries and
  exponential backoff; failures are recorded, never hidden.
- **Free-tier model router.** Gemini free tier, Groq free tier or local Ollama. Paid and
  premium models are locked out by `MATT_FREE_MODELS_ONLY` (on by default); if you ever unlock
  them they stop at your daily and monthly INR budget and ask you in Approvals.
- **Website opportunity pipeline.** Discover businesses on OpenStreetMap by city and category,
  audit their websites (UX, design, SEO, mobile, performance, conversion, technical), rank leads,
  and draft outreach that waits for your approval.
- **Opportunity engine** with the spec's scoring formula, manual or AI-researched.
- **Autopilot** (on by default; the owner can pause it on the Command Center or say "stop autopilot"): on a schedule the
  CEO picks the next most valuable step: the daily CEO report, finding and auditing leads in
  your target cities and niches, opportunity research, and outreach drafts that wait in
  Approvals. It never sends, spends or publishes by itself.
- **Alexa-style commands** that need no AI key: "how much did we earn today", "record 15k
  received for a website project", "which skills are earning", "what's pending", "top leads",
  "remember that...", "open revenue", "what time is it". Anything else goes to MATT's brain, a
  conversational agent that answers any question, remembers the conversation and can hand
  work to the team (find leads, audit, research, assign a skill, run a bot). Skill bots work in
  parallel, one per connected free AI provider, each remembering its past experiments, and
  hand you ready-to-use earning steps. MATT never signs in to your accounts.
- **Sales Desk (the path to a first payment):** each found business with a weak or missing
  website gets a free one-page demo website (private, unindexed preview link at `/p/<token>`,
  built from its public listing) and a personal offer that links to it, a price you set and
  a UPI payment request in your name. One tap opens WhatsApp or email on your own device with the message ready; MATT
  sends nothing itself. Press Paid when the money arrives and it is recorded as revenue.
- **Receive-only money (main rule):** customers pay the owner's own UPI ID directly through a
  payment request (QR code and `upi://pay` link). MATT never sends, transfers, withdraws or
  debits money, enforced in code; a payment counts as revenue once the owner confirms it. The
  owner adds bank and UPI details in Settings (encrypted, masked, audit-logged).
- **Skills that run their own ideas:** on autopilot each skill proposes a small money-making
  experiment in its field and works it step by step, saving its work to Memory. Approvals are
  asked only when an idea needs money; everything else runs on its own within anti-spam and
  legal guardrails.
- **Earnings:** today, 7-day, month and total revenue from the ledger (business timezone
  `MATT_TIMEZONE`, default Asia/Kolkata), a 30-day daily series, revenue by stream, and which
  skills earned it.
- **Command endpoint** for typed or spoken commands, an event feed, a live dashboard and
  analytics computed from stored records.
- **Business records:** customers, products, a revenue and expense ledger (facts you enter),
  experiments, and memory with retention.
- Auth with Google or password, RBAC, audit log, approval gate for risky actions.

Not built yet: sending email (approved drafts are marked ready for you to send), web search,
CRM/calendar/GitHub integrations, the Skill Factory and AI University (Phase 7), and production
hardening (Phase 8). The Tools page lists each one as not connected.

Without an AI key, MATT still discovers and audits businesses, scores opportunities and tracks
records; anything that needs reasoning says so plainly.

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

## Deploy

One click on Render's free tier with `render.yaml`, or Docker Compose on any VM. See
[deployment](docs/deployment.md).

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
    services/     business rules (registry, auth, tasks, approvals, command, dashboard)
    agents/       agent runtime: prompts, untrusted-data fencing, delegation
    llm/          model providers and the free-first budgeted router
    plugins/      tools: website auditor, business discovery, web fetch
    workflows/    code-defined workflows
    worker.py     background task worker
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
