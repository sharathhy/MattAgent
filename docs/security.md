# Security

## In place (Phase 1)

- **Authentication:** bcrypt password hashes; HS256 JWT access tokens with expiry. Owner account
  can only be bootstrapped while no users exist. In production the web bootstrap needs the
  `MATT_BOOTSTRAP_TOKEN` setup code (compared in constant time, rate limited), or is disabled
  when no code is configured. Google sign-in verifies ID tokens server-side (signature, audience,
  issuer, expiry, verified email); only `MATT_OWNER_EMAIL` can become owner, and only while no
  accounts exist. Google-only accounts have no usable password.
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

## Agents and outbound requests

- **Prompt-injection defence:** external content (web pages, business data, task context) is
  passed to models only inside `<untrusted_data>` tags with a standing instruction never to
  follow it. Agents have no tool that sends, spends or publishes; such actions become approvals,
  and delegation is limited to an agent's direct reports and three levels deep.
- **Approval gate:** outreach is high risk and only the owner can approve it; budget overruns
  can be approved by an admin. Every decision is audited.
- **SSRF protection:** `app/core/net.py` allows only http(s) on ports 80/443, rejects
  credentials in URLs and internal hostnames, resolves the host and blocks private, loopback,
  link-local and reserved addresses, re-checks every redirect hop, and caps size (2 MB) and time.
- **Data minimisation:** only public business listings are stored, with their source; an admin
  can delete a business and its lead on request.

## Planned with the capabilities that need them

- **Sandboxed code execution and plugin vetting (Phase 7).** No agent can run code today.

## Reporting

Report vulnerabilities privately to the repository owner rather than in a public issue.

## Money: receive-only (main rule)

MATT only ever receives money, straight into the owner's own UPI account (for example PhonePe).
It never holds funds and has no code path that sends, transfers, withdraws, refunds or debits
money. This is enforced in code, above the approval gates:

- `app/core/money.py` detects outbound-money requests. Tasks (including agent delegations) and
  voice or typed commands that ask to move money out are refused, even if someone would approve.
- Every agent's rules forbid planning or delegating outbound payments.
- `app/services/payments.py` only creates UPI payment requests (a `upi://pay` link and QR code
  addressed to `MATT_UPI_ID`). A test fails if a function there is ever named like a payout.
- MATT cannot see the owner's UPI account, so a request becomes revenue only when the owner
  confirms the money arrived. The UPI ID is set only in the hosting environment, never in the
  repository.
