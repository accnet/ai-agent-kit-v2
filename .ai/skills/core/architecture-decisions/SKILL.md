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
Capture cross-cutting design choices with explicit trade-offs, constraints, and rollback implications.

## When to use
Any decision affecting module boundaries, ownership, lifecycle state, contracts, scalability, or long-term maintenance.

## Procedure
1. State the decision question, scope, and constraints (security, latency, operability, compatibility).
2. List viable alternatives and why each was rejected for this context.
3. Describe selected architecture and its expected impacts on code, tests, rollout, and operations.
4. Record migration/backward-compatibility and rollback strategy.
5. Link the decision to concrete acceptance criteria and verification evidence.

## Checklist
- [ ] Decision includes explicit alternatives and rationale.
- [ ] Impacts to APIs/data contracts are identified.
- [ ] Operational implications (observability, deployment, rollback) are documented.
- [ ] Risks and open questions are tracked with owners.
- [ ] Decision is referenced in task plan/evidence artifacts.

## Anti-patterns
- Landing cross-cutting changes without documenting trade-offs.
- Using "future work" as a substitute for rollback planning.
- Treating implementation detail notes as architecture decisions.

## Output
Architecture note/ADR-quality decision summary linked to tasks and evidence.
