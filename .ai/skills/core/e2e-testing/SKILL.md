---
name: e2e-testing
description: Verify critical user journeys across real boundaries with deterministic environments and fixtures.
version: 2.0.0
tier: core
stack: [any]
owner: qa
gates: [G2]
related: []
---

# Skill: e2e-testing

## Purpose
Validate full user or system journeys across real boundaries before marking work complete.

## When to use
Changes cross API/UI/provider boundaries, affect critical paths, or alter workflow orchestration.

## Procedure
1. Define the smallest high-value end-to-end scenarios impacted by the change.
2. Prepare deterministic test data and environment setup/teardown.
3. Execute journey tests through public interfaces, not internal helpers.
4. Assert user-visible/system-visible outcomes and critical side effects.
5. Capture artifacts for failures (logs/traces/screenshots) and link to evidence.

## Checklist
- [ ] Scenario covers changed boundary behavior end-to-end.
- [ ] Test data is deterministic and isolated.
- [ ] Assertions verify outcome and side effects.
- [ ] Failure artifacts are retained for debugging.
- [ ] E2E checks are scoped to avoid duplicating all unit tests.

## Anti-patterns
- Relying only on unit tests for boundary-crossing changes.
- Flaky E2E tests using sleeps instead of explicit conditions.
- Skipping cleanup, causing cross-test interference.

## Output
E2E evidence demonstrating impacted journeys still work.
