---
name: contract-testing
description: Verify producer-consumer compatibility for public APIs, events, and schemas.
version: 2.0.0
tier: core
stack: [any]
owner: qa
gates: [G2]
related: []
---

# Skill: contract-testing

## Purpose
Verify producer-consumer compatibility for public APIs, events, and schemas.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Define examples at the boundary, validate both success and error responses, run compatibility checks before release, and version breaking changes deliberately.

## Checklist
- [ ] Success and error schemas are tested
- [ ] Consumer assumptions are represented
- [ ] Breaking changes are versioned
- [ ] Compatibility result is recorded

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
