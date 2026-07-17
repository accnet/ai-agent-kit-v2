---
name: threat-modeling
description: Identify threats, abuse cases, mitigations, and residual risk for a feature before implementation.
version: 2.0.0
tier: core
stack: [any]
owner: security
gates: [G1, G3]
related: []
---

# Skill: threat-modeling

## Purpose
Identify threats, abuse cases, mitigations, and residual risk for a feature before implementation.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Identify assets, actors, trust boundaries, and abuse paths. Rank threats by likelihood and impact, assign mitigations, and turn unresolved risks into tasks.

## Checklist
- [ ] Assets and boundaries are listed
- [ ] Abuse cases have mitigations
- [ ] High-risk paths have acceptance criteria
- [ ] Residual risk has an owner

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
