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
Prepare a verifiable release with compatibility, rollout, rollback, and communication checks.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Confirm all gates, version and changelog, deployment order, migration safety, monitoring, rollback trigger, and explicit production approval.

## Checklist
- [ ] Release notes are complete
- [ ] Rollback is actionable
- [ ] Verification is green
- [ ] Production approval is recorded

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
