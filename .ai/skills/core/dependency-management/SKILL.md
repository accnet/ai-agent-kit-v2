---
name: dependency-management
description: Change dependencies deliberately with compatibility, security, lockfile, license, and rollback awareness.
version: 2.0.0
tier: core
stack: [any]
owner: devops
gates: [G2, G4]
related: []
---

# Skill: dependency-management

## Purpose
Change dependencies safely with compatibility, vulnerability, and rollback discipline.

## When to use
Adding, upgrading, downgrading, or removing third-party libraries, runtimes, or transitive overrides.

## Procedure
1. Confirm project-pinned versions and existing adapter usage before proposing changes.
2. Assess compatibility impact (APIs, runtime, build/test tooling, licensing).
3. Check vulnerabilities for supported ecosystems and avoid introducing known critical/high issues.
4. Apply minimal version changes required to satisfy the task; update lockfiles deterministically.
5. Run targeted and then full verification relevant to impacted code paths.

## Checklist
- [ ] Version choice is justified and minimal.
- [ ] Security/vulnerability check recorded for supported ecosystems.
- [ ] Lockfile and manifests remain consistent.
- [ ] Breaking behavior changes are documented and tested.
- [ ] Rollback plan (previous version/revert path) is known.

## Anti-patterns
- Broad dependency upgrades unrelated to scope.
- Editing lockfiles manually without package manager tooling.
- Ignoring transitive dependency impact on runtime behavior.

## Output
Dependency diff + compatibility/security evidence + test evidence.
