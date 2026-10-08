# Roadmap

Each phase ships working, tested functionality before the next begins. Anything not yet built
is shown as "Coming soon" in the UI; nothing is simulated.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Foundation: repository, backend, frontend, database, auth, config, logging, agent registry | Done |
| 2 | Orchestration: tasks, workflows, agent runtime, tool registry, event bus (Redis + worker queue), free-first model router with budgets | Next |
| 3 | Command center: live dashboard over WebSockets, approval center, analytics, agent activity | Planned |
| 4 | Business intelligence: opportunity engine and scoring, business discovery via legitimate APIs, website auditor, leads | Planned |
| 5 | Revenue engines: website service, AI SaaS factory, content and rights-cleared clipping, experiments, revenue portfolio | Planned |
| 6 | Voice: speech-to-text, intent parsing, text-to-speech | Planned |
| 7 | Self-evolving workforce: Skill Factory, AI University, benchmarking, versioned upgrades | Planned |
| 8 | Hardening: security, observability, load tests, backups, disaster recovery | Planned |

## Phase 2 plan

1. `tools`, `tasks`, `workflows`, `events`, `model_usage` tables.
2. Tool Registry with schema-validated inputs/outputs and risk level; tool calls checked against
   agent permissions outside the model.
3. Event bus on Redis streams; long-running work on a worker queue with retry limits and
   exponential backoff (retry → alternative tool → alternative agent → human → fail).
4. Model router: local/free models first, then free tiers, credits, low-cost, and premium only
   within `MATT_DAILY_AI_BUDGET` / `MATT_MONTHLY_AI_BUDGET`; stop and ask when limits are hit.
5. Orchestrator v1: objective → tasks → skill assignment → execution → validation → audit.

## Adding an agent

Add an entry under the right category in `backend/app/registry/data/workforce.yaml` and run
`uv run matt seed-registry`. The catalog tests validate slugs, reporting lines, dependencies and
permissions. From Phase 7 the Skill Factory proposes new agents for owner approval.

## Revenue stages

The long-term target (₹10 crore) is a goal, not a promise. Stages and their priorities:

| Stage | Priority |
| --- | --- |
| ₹0 → ₹10K → ₹1L | Cash flow and validation: one service offer, manual-assist delivery |
| ₹1L → ₹10L → ₹50L | Productization and recurring revenue |
| ₹50L → ₹1Cr → ₹5Cr → ₹10Cr | Scale, automation and management |
