---
name: security-review
description: Review authentication, authorization, input handling, secrets, dependencies, and privacy impact before delivery.
version: 2.0.0
tier: core
stack: [any]
owner: security
gates: [G2, G3]
related: []
---

# Skill: security-review

## Purpose
Review authentication, authorization, input handling, secrets, dependencies, and privacy impact before delivery.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Map trust boundaries and data sensitivity. Inspect every changed entry point for authn/authz, validation, injection, secret exposure, and unsafe defaults. Record severity and remediation.

## Checklist
- [ ] Changed trust boundaries are documented
- [ ] Authorization is checked server-side
- [ ] Untrusted input is validated and encoded
- [ ] No secrets or sensitive logs are introduced

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
