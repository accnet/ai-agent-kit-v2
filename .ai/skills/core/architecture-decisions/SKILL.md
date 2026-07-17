---
name: architecture-decisions
description: Capture durable architecture decisions with alternatives, consequences, and review points.
version: 2.0.0
tier: core
stack: [any]
owner: architect
gates: [G1, G3]
related: []
---

# Skill: architecture-decisions

## Purpose
Capture durable architecture decisions with alternatives, consequences, and review points.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
State the decision context, constraints, alternatives, chosen option, consequences, migration or rollback, and the date for reconsideration.

## Checklist
- [ ] Decision has alternatives
- [ ] Consequences are explicit
- [ ] Rollback or migration is known
- [ ] Decision is linked to tasks

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
