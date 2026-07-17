---
name: workflow-orchestration
description: Operate multi-agent tasks through ownership, DAG dependencies, evidence, retries, and recovery.
version: 2.0.0
tier: core
stack: [any]
owner: scheduler
gates: [G1, G2, G3]
related: []
---

# Skill: workflow-orchestration

## Purpose
Operate multi-agent tasks through ownership, DAG dependencies, evidence, retries, and recovery.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Validate task ownership and dependencies, route minimal context, record claims and evidence, block with a reason, and retry only after the cause is known.

## Checklist
- [ ] DAG is valid
- [ ] Ownership is unambiguous
- [ ] Transition evidence is recorded
- [ ] Blocked work has a recovery action

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
