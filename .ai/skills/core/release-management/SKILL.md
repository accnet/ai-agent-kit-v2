---
name: release-management
description: Prepare a verifiable release with compatibility, rollout, rollback, and communication checks.
version: 2.0.0
tier: core
stack: [any]
owner: release
gates: [G3, G4, G5]
related: []
---

# Skill: release-management

## Purpose
Prepare and ship changes with explicit readiness checks, rollout plan, and rollback strategy.

## When to use
Tasks touch CI, packaging, deployment, migrations, runtime configuration, or release communication.

## Procedure
1. Confirm release scope, dependencies, and risk classification.
2. Verify required checks pass (tests, gates, security, compatibility).
3. Define rollout strategy (phased/canary/full) and observability checkpoints.
4. Prepare rollback steps and data migration safety notes.
5. Publish release notes including behavior changes and operational actions.

## Checklist
- [ ] All release gates and required checks are green.
- [ ] Rollout and rollback instructions are concrete.
- [ ] Operational owners and monitoring windows are identified.
- [ ] Breaking changes and migration steps are communicated.
- [ ] Post-release validation steps are listed.

## Anti-patterns
- Declaring release-ready without evidence paths.
- Shipping migrations with no rollback/backout story.
- Treating CI green as the only release criterion.

## Output
Release readiness record with rollout/rollback and post-release checks.
