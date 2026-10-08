# Security

## In place (Phase 1)

- **Authentication:** bcrypt password hashes; HS256 JWT access tokens with expiry. Owner account
  can only be bootstrapped while no users exist.
- **Authorization:** RBAC (owner > admin > operator > viewer) enforced per route. Only the owner
  creates users and changes agent permissions; admins can move agents through the lifecycle.
- **No silent escalation:** agent permission changes are owner-only, versioned and audited, with
  high-risk grants called out in the audit entry.
- **Audit log:** every state change is recorded with actor, target, details and request id.
- **Secrets:** read from environment variables only (`MATT_*`). Production refuses to start with
  the default or a short `MATT_SECRET_KEY`, or with SQLite.
- **Input validation:** Pydantic schemas on every request; enum-validated permissions/statuses.
- **Rate limiting:** login attempts limited per client and email.
- **Headers:** `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP, and
  `Permissions-Policy` on API responses; nginx adds a CSP for the web app. Request ids are
  validated before being echoed.
- **Least privilege at runtime:** containers run as a non-root user; API docs are disabled in
  production.

## Known limitations (tracked for Phase 8)

- The access token is stored in `localStorage`; move to an httpOnly, SameSite cookie with CSRF
  protection.
- The login rate limiter is in-process; move to Redis for multi-process deployments.
- No refresh tokens or token revocation yet; keep `MATT_ACCESS_TOKEN_MINUTES` short.
- Dependency scanning (e.g. `pip-audit`, `npm audit`, Dependabot) is not yet in CI.

## Planned with the capabilities that need them

- **Prompt-injection defence (Phase 2+):** all external content (web pages, emails, documents)
  is passed to models as clearly delimited untrusted data; tool calls are checked against the
  agent's permissions and the approval policy outside the model, so injected text cannot grant
  permissions, approve actions, or reveal secrets.
- **Approval gate (Phase 3):** external actions, spending, publishing, deletion, infrastructure
  and production changes require an owner decision.
- **SSRF and malicious-site protection (Phase 4):** website auditing fetches through an
  allow-listed, private-IP-blocking fetcher with size and time limits.
- **Sandboxed code execution and plugin vetting (Phases 2 and 7).**

## Reporting

Report vulnerabilities privately to the repository owner rather than in a public issue.
