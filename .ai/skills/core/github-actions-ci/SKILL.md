---
name: github-actions-ci
description: Maintain deterministic GitHub Actions validation with least privilege and actionable failures.
version: 2.0.0
tier: core
stack: [any]
owner: devops
gates: [G2, G4]
related: []
---

# Skill: github-actions-ci

## Purpose
Maintain deterministic GitHub Actions validation with least privilege and actionable failures.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Pin actions by supported major or SHA policy, grant minimal permissions, cache safely, run the same checks locally where possible, and protect required checks.

## Checklist
- [ ] Permissions are minimal
- [ ] Checks are deterministic
- [ ] Secrets are scoped
- [ ] Failure logs identify the failed gate

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
