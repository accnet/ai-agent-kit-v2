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
Coordinate multi-task execution with deterministic dependency handling, ownership, and lifecycle integrity.

## When to use
Tasks involve parallel work, blocked dependencies, handoffs, retries, or multi-agent sequencing.

## Procedure
1. Validate dependency graph as acyclic and ownership-defined.
2. Claim runnable work through legal state transitions only.
3. Record handoff payloads, attempt counts, and blocking reasons.
4. Apply retry/resume logic without bypassing QA/review gates.
5. Keep audit trail explaining routing and transition decisions.

## Checklist
- [ ] Dependencies and phase order are explicit and valid.
- [ ] No worker bypasses state manager transitions.
- [ ] Blocked tasks include actionable unblock reason.
- [ ] Handoff data contains required context and acceptance criteria.
- [ ] Audit history explains why and when each transition happened.

## Anti-patterns
- Directly mutating task status outside transition APIs.
- Dispatching tasks with ambiguous ownership or missing acceptance criteria.
- Conflating execution completion with QA/review approval.

## Output
Deterministic orchestration evidence: valid DAG, traceable handoffs, and lawful transitions.
