---
name: security-review
description: Review authentication, authorization, input handling, secrets, dependencies, and privacy impact before delivery.
version: 2.1.0
tier: core
stack: [any]
owner: security
gates: [G2, G3]
related: [threat-modeling]
---

# Skill: security-review

## Purpose
Catch the vulnerability classes that automated tests don't, on every changed
entry point, before a task is marked done.

## When to use
Any task that adds or changes: an API route/handler, auth/session logic, a
database query, a file/URL taking user input, a dependency, or logging of
request data. Run this as part of `review-approve`, not as a separate task.

## Procedure

1. **Map the diff's entry points.** List every new/changed route, webhook,
   CLI flag, cron job, message-queue consumer, or file upload path. Anything
   not in this list is out of scope for this pass — don't review the whole
   repo.
2. **AuthN.** Confirm every new/changed route runs behind the project's real
   auth middleware, not a dev-only bypass that leaked into the shared path.
   Grep for the framework's auth decorator/middleware on each new route file.
3. **AuthZ / IDOR.** For every handler that reads or mutates a specific
   record (`/orders/:id`, `/users/:id/settings`), verify the check is
   "does the *authenticated actor* own or have a role granting access to
   *this specific id*" — not just "is the caller logged in." This is the
   single most common defect this pass catches.
4. **Injection.** SQL/NoSQL/command/template: every query must use
   parameter binding, not string/f-string/template concatenation of
   user input. Grep the diff for raw query builders (`.raw(`, `db.query(` +
   `${}`/`%s`/`+`) and for shell calls built from user input
   (`subprocess.run(f"...")`, `exec(cmd)` with concatenated args).
5. **Secrets.** No literal API keys/tokens/passwords in the diff (`grep -nE`
   the patterns `.ai/scripts/check-gates.sh` already uses). No `.env` file
   added to the diff unless it's `.env.example`. No secret value printed in
   a log/error/exception message.
6. **Deserialization / SSRF.** No `pickle.loads`, `yaml.load` (unsafe
   loader), or framework auto-deserialization of untrusted payloads. Any
   outbound request built from a user-supplied URL is checked against an
   allowlist or otherwise prevented from reaching internal/metadata
   addresses (`169.254.169.254`, `localhost`, RFC1918 ranges).
7. **Output encoding / XSS.** User-controlled data rendered into HTML, a JS
   context (`innerHTML`, template literals inserted into `<script>`), or a
   URL is encoded for that specific context, not just HTML-escaped once and
   reused everywhere.
8. **Dependencies.** New or bumped packages are checked against the
   ecosystem's advisory tool (`npm audit`, `pip-audit`, `cargo audit`, …)
   before merge, and pinned — no wildcard/floating ranges introduced.
9. **Privacy.** Any new field flowing into logs, analytics events, or a
   third-party integration is checked against the project's existing data
   classification (if none exists, treat email/name/IP/free-text fields as
   sensitive by default and flag it).

## Checklist
- [ ] Every new/changed route confirmed behind real auth middleware (not a
      dev bypass)
- [ ] Object-level authorization checked per-record, not just per-session
      (IDOR)
- [ ] All new queries use parameter binding; no string-built SQL/shell
      commands
- [ ] No secrets, tokens, or `.env` (non-example) files in the diff
- [ ] User input reaching HTML/JS/URL output is encoded for that context
- [ ] New/updated dependencies checked against an advisory scanner, pinned
- [ ] New logged/exported fields checked against data-sensitivity
      expectations

## Severity triage
- **Block**: missing authz on a mutating endpoint, injectable query, secret
  in diff, SSRF to internal network reachable from user input.
- **Fix before merge, don't block if isolated**: missing rate limiting on a
  low-value read endpoint, verbose error message leaking a stack trace in a
  non-prod-reachable path.
- **Note, don't block**: dependency has a low-severity advisory with no
  known exploit path in how this project uses it — record it, don't let it
  stall the task.

## Anti-patterns
- Approving because the test suite is green — tests don't cover auth
  bypass or injection unless written specifically for them.
- Reviewing the whole file instead of the entry points actually changed;
  scope creep here just slows delivery without adding coverage.
- Treating "logged in" as equivalent to "authorized for this resource."
- Rubber-stamping AI-generated code without checking the auth/authz path on
  any route it added.

## Output
Record findings as blocking/non-blocking with the exact file:line, the
concrete failure scenario (not just the rule violated), and remediation.
Evidence goes in the `review` evidence JSON (`kind: "review"`); residual,
accepted risk goes in `.ai-work/plan/architecture.md` or the task's
`blocked_reason` if it must stop the task.
