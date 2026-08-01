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
Prevent interface regressions by validating provider-consumer contracts at stable boundaries.

## When to use
Changes to HTTP APIs, events, webhooks, serialized payloads, SDK adapters, or schema-enforced interfaces.

## Procedure
1. Identify contract producer, consumers, and backward-compatibility expectations.
2. Codify required fields, optional fields, and semantic invariants as tests/fixtures.
3. Add negative tests for missing fields, type drift, and unknown enum/state values.
4. Run producer and consumer-side tests (or mocks) against shared fixture/contracts.
5. Document migration plan when breaking changes are unavoidable.

## Checklist
- [ ] Contract fixture/schema updated with version notes.
- [ ] Positive and negative cases exist for changed fields.
- [ ] Consumer compatibility verified for current supported versions.
- [ ] Breaking change path includes explicit migration guidance.
- [ ] Evidence includes contract test command and outputs.

## Anti-patterns
- Only testing happy-path payloads.
- Changing contract shape without consumer proof.
- Using snapshot-only assertions with no semantic checks.

## Output
Updated contract tests/fixtures with compatibility evidence.
