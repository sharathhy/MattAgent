# Roadmap

Each phase ships working, tested functionality before the next begins. Anything not yet built
is shown as "Coming soon" in the UI; nothing is simulated.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Foundation: repository, backend, frontend, database, auth, config, logging, agent registry | Done |
| 2 | Orchestration: tasks, workflows, agent runtime, tool registry, event bus, free-first model router with budgets | Done |
| 3 | Command center: live dashboard, approval center, analytics, agent activity | Done (polling; WebSockets later) |
| 4 | Business intelligence: opportunity engine and scoring, business discovery via OpenStreetMap, website auditor, leads, outreach drafts | Done (email sending not connected) |
| 5 | Revenue engines: customers, products, revenue ledger, experiments | Records done; delivery engines planned |
| 6 | Voice: speech-to-text, intent parsing, text-to-speech | Planned |
| 7 | Self-evolving workforce: Skill Factory, AI University, benchmarking, versioned upgrades | Planned |
| 8 | Hardening: security, observability, load tests, backups, disaster recovery | Planned |

## How Phase 2 was built

- The queue is the `tasks` table, drained by a worker thread inside the web process, because
  Render's free tier has no Redis. Failures retry with exponential backoff up to three attempts;
  an exhausted AI budget parks the task behind an approval instead of failing it.
- The event bus is the `events` table; the UI polls `GET /api/events?after_id=`.
- Untrusted content (web pages, business data) reaches models only inside `<untrusted_data>`
  tags, and agents cannot send, spend or publish: those actions become approvals.

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
