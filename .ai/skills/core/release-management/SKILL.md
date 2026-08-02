---
name: release-management
description: Prepare a verifiable release with compatibility, rollout, rollback, and communication checks.
version: 2.1.0
tier: core
stack: [any]
owner: release
gates: [G3, G4, G5]
related: [deployment-infra, github-actions-ci]
---

# Skill: release-management

## Purpose
Confirm a change is ready to ship, versioned correctly, and can be safely rolled back — distinct
from `deployment-infra`, which handles the mechanics of pushing artifacts to infrastructure.
Release management owns the *decision* to release; deployment-infra owns *how* the push
happens. Neither role crosses into the other.

## When to use
Any task that produces an artifact others will depend on: a versioned library, a service
deployment, a database migration, a configuration change, or a documented breaking change.
Also run before merging to a protected branch when CI gates are required for release approval.

## Procedure

1. **Define and confirm the release scope.** List every component version being changed,
   the target environment (staging, canary, production), and any dependent services that
   must be updated in the same or subsequent release. If the scope is ambiguous, stop and
   clarify — partial releases with undefined scope are a common source of rollback failures.
2. **Verify all required gates are green.** Confirm G2 (tests + evidence) and G3 (review
   approved, no unresolved blockers) are complete for every task in the release scope.
   A release with any task still `in_progress` or `blocked` is not ready. Record the
   CI run URL and test evidence paths in the release record.
3. **Check backward compatibility.** For each changed interface (API shape, event schema,
   configuration key, CLI flag), classify the change as additive, compatible-but-deprecated,
   or breaking. Breaking changes require: an explicit migration guide, a minimum deprecation
   window if consumers exist, and version bump to a new major/minor as appropriate.
4. **Assign a version and update manifests.** Follow semver (or the project's version policy):
   bump patch for bug fixes, minor for additive features, major for breaking changes. Update
   `package.json`, `pyproject.toml`, `CHANGELOG.md`, or whatever the project uses — do not
   release without a version change when behavior has changed.
5. **Define rollout strategy and observability window.** Choose the appropriate rollout:
   - *Full cut-over*: all traffic immediately — only for low-risk or stateless changes.
   - *Canary/phased*: route a subset of traffic first; define the success threshold (error
     rate, latency) and observation window before advancing.
   - *Feature flag*: deploy code off, enable post-validation — useful for data migrations
     or API changes that consumers need advance notice of.
   Specify who monitors the rollout window and what metrics indicate success or rollback.
6. **Write concrete rollback steps.** For each component in the release, document the exact
   rollback command: previous image tag to re-deploy, migration `down` command, feature flag
   to disable, or config value to revert. "Revert the PR" is not a rollback plan; it is a
   source-only step that doesn't touch already-migrated databases or live infrastructure.
7. **Communicate the release.** Publish release notes covering: behavior changes visible to
   users or consumers, breaking changes with migration instructions, deprecated interfaces
   and their sunset date, and operational actions required (restart, cache flush, migration
   run). Record the audience (internal team, API consumers, end-users) and channel (PR
   description, changelog, email, status page).
8. **Define post-release validation.** List the specific checks to confirm the release is
   healthy: key metric thresholds, smoke test commands, or manual verification steps. These
   are not optional — they are what lets you declare the release successful and close G5
   for any destructive operations.

## Checklist
- [ ] Release scope (components, versions, environments) is explicitly stated
- [ ] G2 and G3 are green for every task in scope; CI run URL recorded
- [ ] Breaking changes classified and migration guide written
- [ ] Version bump applied in all relevant manifests; CHANGELOG updated
- [ ] Rollout strategy (full/canary/flag) and monitoring window defined
- [ ] Concrete rollback commands documented (not just "revert the PR")
- [ ] Release notes published to the identified audience and channel
- [ ] Post-release validation steps listed and assigned

## Anti-patterns
- Declaring "CI is green" as the sole release criterion — CI covers tests, not backward
  compatibility, runbook correctness, or operational readiness.
- Shipping a database migration with no `down` path, on the grounds that the rollback
  "probably won't be needed" — this guarantees a downtime incident when it is needed.
- Using the deployment PR as the only release communication — consumers of an API or
  library need more notice than a merged PR.
- Conflating this skill with `deployment-infra`: release management decides *what and when*;
  deployment-infra executes *how*. Don't duplicate infrastructure provisioning steps here.

## Output
Release record in `.ai-work/plan/` or a dedicated release artifact with: scope, gate evidence
links, version bump diff, rollout/rollback plan, release notes, and post-release validation
checklist. G5 approval recorded for destructive operations (e.g., production data migration).
