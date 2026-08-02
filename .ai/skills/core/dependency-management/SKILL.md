---
name: dependency-management
description: Change dependencies deliberately with compatibility, security, lockfile, license, and rollback awareness.
version: 2.1.0
tier: core
stack: [any]
owner: devops
gates: [G2, G4]
related: [github-actions-ci, security-review]
---

# Skill: dependency-management

## Purpose
Change third-party dependencies safely so that every addition, upgrade, or removal is
intentional, security-checked, minimally scoped, and reversible — with no silent lockfile
drift or transitive surprises that break CI or introduce vulnerabilities.

## When to use
Adding a new package, upgrading or downgrading a direct dependency, resolving a transitive
vulnerability, removing an unused dependency, or updating a runtime/tooling version (Node,
Python, Go, JDK). Also applies to `devDependencies` and CI action versions that affect
reproducibility.

## Procedure

1. **Check existing usage before proposing a change.** Before adding a new library, grep the
   codebase for the capability it provides — the project may already have an equivalent
   utility or an approved adapter. Adding a second library for the same purpose increases
   surface area without benefit. If an existing library covers 80% of the need, prefer
   extending it over adding a new one.
2. **Choose the minimum version that satisfies the need.** Select the smallest version bump
   that resolves the issue or enables the feature: patch bump for a bug fix, minor bump for
   a new API, major bump only when unavoidable. Do not pull in the latest version
   speculatively — every version jump introduces new transitive changes.
3. **Scan for known vulnerabilities.** Before finalizing any new or changed direct dependency,
   run the advisory scanner for the ecosystem:
   - npm/Node: `npm audit` (or `pnpm audit`, `yarn audit`)
   - Python: `pip-audit` or `safety check`
   - Go: `govulncheck ./...`
   - Rust: `cargo audit`
   - Java: `mvn dependency-check:check` or `gradle dependencyCheckAnalyze`
   Record the scanner output as evidence (G4). Do not introduce a package with a known
   Critical or High vulnerability — if no safe version exists, escalate before proceeding.
4. **Check the license.** Verify the new package's license is compatible with the project's
   license policy (typically: permissive licenses like MIT/Apache-2.0/BSD are acceptable;
   copyleft like GPL requires review). If the project has a `license-checker` or similar
   tool, run it after the change.
5. **Update lockfiles with the package manager, not by hand.** Run `npm install`, `pip-compile`,
   `go mod tidy`, `cargo update`, or the equivalent — never edit `package-lock.json`,
   `Pipfile.lock`, `go.sum`, or `Cargo.lock` directly. Commit both the manifest change
   (`package.json`, `requirements.in`, `go.mod`, `Cargo.toml`) and the updated lockfile
   together. A manifest change without a lockfile update is incomplete and will diverge
   across environments.
6. **Verify reproducibility.** After the lockfile update, run a clean install from the
   lockfile in a fresh environment (or `npm ci` / `pip-sync` equivalent) and confirm the
   target tests pass. This catches cases where the lockfile resolves to a different version
   than expected, or where a transitive dependency changed behavior.
7. **Document breaking API changes.** If the upgrade changes an API the project uses (renamed
   method, removed export, changed parameter), update every call site in the same PR. Do not
   leave a `// TODO: update after upgrade` comment and merge — this is a broken state in CI.
   Record the migration in the PR description or `.ai-work/plan/architecture.md`.

## Checklist
- [ ] Existing alternatives checked before adding a new library
- [ ] Version choice is the minimum that satisfies the need; not a speculative latest bump
- [ ] Advisory scanner run and output recorded; no new Critical/High vulnerabilities introduced
- [ ] License is compatible with project policy
- [ ] Both manifest and lockfile updated using the package manager, not manual edits
- [ ] Clean install from lockfile verified; target tests pass
- [ ] All call sites updated for any breaking API change in the upgraded package

## Anti-patterns
- Running `npm install --save-exact latest` for every new feature, resulting in a PR that
  bumps 40 transitive dependencies with no stated reason — reviewers cannot assess the risk.
- Editing `package-lock.json` or `go.sum` by hand to "fix a conflict" — the result is a
  lockfile that diverges from what the package manager would generate, breaking reproducible
  builds.
- Adding a dependency to bypass a missing feature in the current version of an already-used
  library without first checking if the current version can be upgraded to include that
  feature natively.
- Merging a security advisory upgrade without running the scanner post-upgrade — transitive
  advisories can shift when a direct dependency changes.

## Output
Updated manifest + lockfile in a single commit, with advisory scanner output as evidence,
license check result, and a short PR note explaining the change rationale and any API
migration steps.
