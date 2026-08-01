---
name: github-actions-ci
description: Maintain deterministic GitHub Actions validation with least privilege and actionable failures.
version: 2.1.0
tier: core
stack: [any]
owner: devops
gates: [G2, G4]
related: [deployment-infra, release-management]
---

# Skill: github-actions-ci

## Purpose
Keep CI fast, deterministic, least-privilege, and diagnosable from the
failure log alone — no "re-run and see if it passes."

## When to use
Adding or editing a `.github/workflows/*.yml` file, a composite/reusable
action, or a required status check.

## Procedure

1. **Least privilege.** Set `permissions:` at the workflow (or job) level
   explicitly; don't rely on the repo default, which is often broader than
   the job needs. A job that only runs tests needs `contents: read` and
   nothing else; only jobs that push tags, comment on PRs, or publish
   packages get write scopes, and only the ones they need.
2. **Pin third-party actions by commit SHA**, not a mutable tag (`@v4` can
   be repointed by the action's maintainer or a compromised account); first-
   party `actions/*` at a major-version tag is an acceptable, common
   exception — decide per-project and be consistent.
3. **Cache correctly.** Key `actions/cache` (or the language-specific
   cache in `setup-node`/`setup-python`) off the lockfile hash
   (`hashFiles('**/package-lock.json')`), not a static string — a stale key
   silently serves outdated dependencies across cache hits.
4. **Concurrency.** Add a `concurrency: { group: ..., cancel-in-progress:
   true }` keyed on the ref for CI workflows, so superseded pushes on the
   same PR/branch don't queue redundant runs burning minutes.
5. **Determinism.** Pin the language/runtime version explicitly
   (`node-version`, `python-version`); don't float on `latest`. Avoid steps
   whose outcome depends on wall-clock time or external network state
   without a retry/backoff (flaky external calls should be mocked in CI,
   not hit live).
6. **Secrets.** Never `echo`/`print` a secret, even redacted-looking. Avoid
   `pull_request_target` combined with checking out the PR head ref when
   secrets are in scope — that combination lets a forked PR's code run with
   your repo's secrets. Use `pull_request` (no secrets, read-only token)
   for anything that builds/executes untrusted contributor code.
7. **Actionable failures.** Each job/step name should say what gate it
   checks (`Engine tests`, `Validate kit contracts`) so a failing check's
   name alone tells a reader what broke, without opening the log — this
   repo's own `.github/workflows/gates.yml` follows this already.
8. **Required checks.** Confirm the checks intended to gate merges are
   actually configured as required status checks on the branch protection
   rule — a green workflow that isn't required doesn't block anything.

## Checklist
- [ ] `permissions:` set explicitly and scoped to what the job does
- [ ] Third-party actions pinned by SHA (or a documented, consistent
      tag policy)
- [ ] Cache key derived from the lockfile hash, not a static string
- [ ] `concurrency` group cancels superseded runs on the same ref
- [ ] No secret-bearing workflow checks out untrusted PR head code
      (`pull_request_target` + checkout of head)
- [ ] Job/step names identify the gate they check
- [ ] Checks intended to block merges are set as required in branch
      protection

## Anti-patterns
- `permissions: write-all` because a narrower scope "didn't work" without
  first checking which specific scope the failing step actually needs.
- A cache key that never changes ("stale cache forever") or one keyed on
  the run ID ("cache never hits").
- `continue-on-error: true` on a check that's supposed to gate merges —
  this makes it green regardless of outcome.
- Re-running a flaky job instead of fixing or removing the source of
  flakiness (unmocked network call, shared test-order dependency, race in
  parallel test workers).

## Output
The workflow diff itself is the evidence; link the CI run and the specific
job/step names changed in the review evidence JSON.
