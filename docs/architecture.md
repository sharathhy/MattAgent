# Architecture

## Principles

- MATT is a platform, not a prompt: agents, tools and workflows are data plus small services.
- Clean layering in the backend: `api` → `services` → `repositories` → `models`. Routes hold no
  business rules; services raise typed `ServiceError`s that map to HTTP status codes.
- Everything that changes state writes an `audit_logs` row in the same transaction.
- Facts only. Metrics are NULL until measured; the UI says "No data yet", and tools that are not connected are labelled as such.

## Data model (Phase 1)

| Table | Purpose |
| --- | --- |
| `users` | Human accounts with a role (owner, admin, operator, viewer). Exactly one owner. |
| `agents` | Every worker: CEO, executives, skills, meta-skills. Holds the spec's worker fields (role, capabilities, inputs, outputs, tools, permissions, cost tier, dependencies, version, status, performance, success rate, revenue contribution, timestamps) and `parent_id` for the org chart. |
| `agent_versions` | Immutable snapshot of each definition change. |
| `audit_logs` | Who did what to which target, with request id. |

Later phases add the remaining entities from the spec (tasks, workflows, tools, events,
approvals, businesses, leads, revenues, expenses, experiments, model_usage, knowledge…) as new
migrations. Migrations are never destructive without an explicit, reviewed migration.

## Workforce catalog

`backend/app/registry/data/workforce.yaml` defines the initial workforce compactly: the CEO,
executives, and skill categories with defaults (department, reporting line, tools, permissions,
cost tier). `matt seed-registry` inserts agents that are not yet registered and never
overwrites existing rows, so owner changes survive re-seeding. The loader validates unique
slugs, known reporting lines and dependencies, and valid permissions.

Reporting lines: Business → CFO, Sales → CRO, Marketing and Content → CMO, AI SaaS and Design →
CPO, Software Engineering → CTO, Research and Operations → COO, Intelligence → CEO,
self-upgrade meta-skills → CHRO.

## Agent lifecycle

```text
discovered → designed → built → testing → evaluated → deployed → upgrading → testing …
                         ↑__________|__________|                      (any) → retired
```

A failed test or evaluation returns to `built`. An upgraded agent must pass testing and
evaluation again before redeploying; there is no shortcut to `deployed`. Catalog agents start at
`designed`: defined, not yet executable.

## Permissions

Agent permissions: `read`, `write`, `external_action`, `financial`, `admin`. The last three are
high-risk; agents holding them are flagged `requires_approval`. Only the owner can change an
agent's permissions (versioned and audited); no API path lets an agent change its own.

## Frontend

React 19 + TypeScript (strict) + Tailwind 4 + TanStack Query + React Router. Every page in
`src/lib/navigation.ts` is backed by a live API; lists refresh by polling.

## Orchestration

`POST /api/command` maps clear requests ("find gyms in Mysore", "audit example.com", "status")
to deterministic workflows and sends everything else to MATT's brain (`app/services/chat.py`):
a conversational agent with a live briefing, the last few turns of the conversation (memory
kind `chat`, kept 30 days) and tools it calls with `DO <tool>: <argument>` lines (find, audit,
research, assign, bot, remember, change_code, autopilot). Agent tasks can still delegate with
`DELEGATE <slug>: <objective>` lines to direct reports. Skill bots run in batches, one per free
provider (`ModelRouter.lanes()`, `prefer=`), on `MATT_WORKER_THREADS` parallel workers. Tasks are rows in `tasks`, claimed by
the worker (`SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL), executed through the model
router, and recorded with model, tokens and INR cost. Every step writes to `events`.
