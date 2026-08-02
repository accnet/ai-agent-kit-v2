---
name: contract-testing
description: Verify producer-consumer compatibility for public APIs, events, and schemas.
version: 2.1.0
tier: core
stack: [any]
owner: qa
gates: [G2]
related: [api-contract, integration-contracts, e2e-testing]
---

# Skill: contract-testing

## Purpose
Catch interface regressions between a producer (the service or library that defines a
contract) and its consumers (callers, event subscribers, SDK users) before they reach
a shared environment. Contract tests are faster, more targeted, and more reliable than
full E2E tests for this class of regression — they fail immediately when the shape
or semantics of an interface diverge, not when the first consumer breaks in staging.

## When to use
Any change to: an HTTP response shape, a published event payload, a serialized DTO,
a database read model consumed by another service, an SDK's exported type, or a
gRPC/GraphQL schema. Also use when onboarding a new consumer that must not break
if the producer changes.

## Procedure

1. **Identify the contract, its producer, and all current consumers.** The producer is
   the service or module that defines the schema; consumers are anything that reads and
   parses it. Grep the codebase and any related repos for usages of the changed type,
   endpoint path, or event name. A consumer you didn't find is a consumer you'll break.
2. **Codify the contract as a versioned fixture or schema.** Write or update a fixture
   file (JSON, YAML, Avro schema, OpenAPI fragment, or TypeScript type snapshot) that
   represents the current stable contract. Store it in a location both producer and
   consumer tests can reference — typically `tests/contracts/` or `fixtures/`. Give it
   a version label so changes are traceable.
3. **Write producer-side tests.** The producer's tests assert that its output matches
   the contract fixture: required fields are present with the correct types, optional
   fields are absent or correctly typed when present, and no undocumented fields are
   included in responses that consumers might accidentally rely on.
4. **Write consumer-side tests against the fixture.** The consumer's tests assert that
   its parser/adapter correctly handles the contract fixture: it reads required fields,
   tolerates unknown fields (forward compatibility), and handles missing optional fields
   without throwing. Use a mock server or stub that returns the fixture, not a live
   service call.
5. **Add negative tests for failure modes.** At minimum: missing required field → consumer
   returns a typed error (not an exception); unexpected enum value → consumer handles it
   gracefully; wrong field type (string where int expected) → producer test fails
   fast, not silently coerces. These tests catch the most common silent contract drift.
6. **Define the compatibility expectation.** Decide and document whether the contract is
   "backward compatible" (consumers on old contract still work), "forward compatible"
   (producers can add fields consumers don't know about), or "versioned breaking change"
   (requires a migration window). A breaking change requires a migration plan and explicit
   consumer notification before the producer ships — not after.
7. **Run both producer and consumer test suites before merge.** If producer and consumer
   live in different repos, coordinate the fixture version bump through a shared contract
   repo or a package version pin. Do not merge the producer change until the consumer
   tests are green against the new fixture.

## Checklist
- [ ] Contract fixture/schema file created or updated with a version label
- [ ] Producer tests assert required fields, types, and absence of undocumented extras
- [ ] Consumer tests assert parsing correctness against the fixture (not a live call)
- [ ] Negative tests cover missing required fields, unexpected enum values, and type drift
- [ ] Compatibility expectation (backward/forward/versioned-breaking) is documented
- [ ] Breaking changes have a migration plan and consumer notification before producer ships
- [ ] Both producer and consumer test suites pass against the updated fixture

## Anti-patterns
- Only testing the happy-path payload from the producer, leaving consumers unverified —
  this detects zero regressions when a field is removed or renamed.
- Using snapshot-only assertions (`toMatchSnapshot()`) with no semantic checks — snapshots
  fail on any whitespace change and pass silently when a semantic invariant breaks.
- Changing the contract shape and fixing only the producer's tests without verifying the
  consumer — the regression surfaces in the next integration environment, not in CI.
- Treating E2E tests as the contract safety net — they are too slow, too brittle, and too
  coarse-grained to reliably catch schema drift on every PR.

## Output
Updated contract fixture in `tests/contracts/` (or equivalent), producer tests asserting
contract conformance, consumer tests asserting parsing correctness, and a PR note recording
the compatibility classification and any migration steps required.
