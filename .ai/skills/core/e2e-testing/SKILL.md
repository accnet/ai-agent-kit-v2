---
name: e2e-testing
description: Verify critical user journeys across real boundaries with deterministic environments and fixtures.
version: 2.1.0
tier: core
stack: [any]
owner: qa
gates: [G2]
related: [contract-testing, test-and-validation]
---

# Skill: e2e-testing

## Purpose
Verify that the system's most critical user journeys still work end-to-end after a change —
across real service boundaries, real databases, and real protocol encodings — before the
change reaches a shared environment. E2E tests are slow and costly; they should cover only
the journeys that unit and contract tests cannot reach, not replicate every unit test at a
higher level.

## When to use
Changes that: cross an API/UI/queue/provider boundary, alter a multi-step workflow sequence,
change how a user completes a critical action (signup, checkout, deploy, publish), or modify
workflow orchestration logic that coordinates multiple services or agents. Do not add E2E
tests for pure logic changes that are better covered by unit tests, or for interface contract
changes that are better covered by contract tests.

## Procedure

1. **Select the smallest set of high-value scenarios.** Map the change to the user journeys
   it affects. Choose the one or two journeys that are: highest business value (failure would
   be immediately noticed by users), hardest to cover with lower-level tests (require real
   boundary crossing), and most likely to regress given the change. Document the scenario
   with a clear precondition, action sequence, and expected observable outcome — not in terms
   of implementation details, but in terms of what the user or calling system would see.
2. **Prepare a deterministic test environment.** The E2E environment must be reproducible:
   - Database seeded from a known fixture (not a snapshot of production); each test run
     starts from the same state, using transactions or teardown scripts to reset between runs.
   - External dependencies replaced with fakes, contract-verified stubs, or a test instance
     of the real service — never a shared staging environment that other tests pollute.
   - Time-dependent behavior (tokens, scheduled jobs, expiry) controlled through injectable
     time or test-mode overrides, not by waiting with `sleep()`.
3. **Exercise journeys through public interfaces only.** Drive the test through the same
   surface a real user or external caller would use: HTTP endpoints, browser interactions,
   CLI commands, or message queue publications. Do not call internal service methods directly
   to set up state or verify outcomes — that makes the test bypass the boundaries it's
   supposed to validate.
4. **Assert user-visible or system-visible outcomes and side effects.** Verify what the user
   or caller receives (response body, rendered UI state, returned data), not just the HTTP
   status code. Also assert the observable side effects: the database row was created, the
   email was sent to the mock SMTP server, the downstream event was published. Avoid asserting
   internal state (private fields, in-memory cache contents) that doesn't represent a
   behavioral outcome.
5. **Capture failure artifacts immediately.** Configure the test runner to retain, on failure:
   server logs for the duration of the test, HTTP request/response traces (for API E2E),
   browser screenshots and console logs (for UI E2E), and any queue/event messages sent
   during the test. These artifacts are the only way to diagnose an E2E failure that can't
   be reproduced locally — don't make them opt-in.
6. **Enforce deterministic wait conditions.** Replace every `sleep(N)` or `time.sleep(N)`
   with an explicit poll-and-assert (retry with a short interval until the expected state
   appears, or until a timeout fires and the test fails). `sleep` values are always wrong
   in either direction: too short causes intermittent failures; too long makes the suite slow.
   Use the test framework's async wait utilities (`waitFor`, `poll`, `retry`) with a
   reasonable timeout and a clear failure message.

## Checklist
- [ ] Scenario documented with precondition, action sequence, and expected observable outcome
- [ ] Test environment is deterministic: seeded from known fixtures, reset between runs
- [ ] All external dependencies use fakes/stubs, not a shared staging environment
- [ ] Test drives the system through public interfaces only (no direct internal method calls)
- [ ] Assertions cover both return values/UI state and observable side effects
- [ ] Failure artifacts (logs, traces, screenshots) are captured automatically on failure
- [ ] No `sleep()` calls; all wait conditions use explicit poll-and-assert with timeouts

## Anti-patterns
- Adding an E2E test for every unit-testable behavior because "it's more realistic" —
  the suite becomes slow, fragile, and provides no additional signal over the unit tests.
- Using `sleep(5)` for async operations — this makes the test intermittently flaky when
  the system is slower than expected, and wastes time when it's faster.
- Sharing test state across runs (a common database row created once for all tests) —
  the first passing run leaves state that makes the second run pass or fail unpredictably.
- Testing through internal methods ("call the service layer directly for the setup, then
  check the HTTP response") — this bypasses the boundary and makes the test insensitive
  to a broken request parsing layer.

## Output
E2E test files targeting critical journeys, environment setup/teardown scripts or fixtures,
and a test run report with pass/fail evidence (command, output, failure artifacts if any)
recorded in the task note.
