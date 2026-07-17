---
name: integration-contracts
description: Design reliable contracts with external services, APIs, events, and asynchronous consumers.
version: 2.0.0
tier: core
stack: [any]
owner: integration
gates: [G1, G2]
related: []
---

# Skill: integration-contracts

## Purpose
Design reliable contracts with external services, APIs, events, and asynchronous consumers.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Define request and response schema, ownership, timeouts, error taxonomy, compatibility, and observability. Verify provider failures and consumer compatibility.

## Checklist
- [ ] Contract and ownership are explicit
- [ ] Timeout and error behavior are defined
- [ ] Compatibility is tested
- [ ] Failure responses are observable

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
