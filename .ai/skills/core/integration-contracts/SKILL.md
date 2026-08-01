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
Keep external API/provider integrations robust, version-aware, and contract-verified.

## When to use
Any outbound API call, webhook consumer, event ingestion, or third-party SDK behavior change.

## Procedure
1. Identify external contract version and current adapter implementation.
2. Define request/response/error schema expectations and timeout/retry behavior.
3. Validate signatures/authentication and idempotency requirements where applicable.
4. Add or update contract tests/mocks for success and failure classes.
5. Document operational runbook updates (rate limits, fallback, degraded mode).

## Checklist
- [ ] Contract schema/fixtures updated for changed fields.
- [ ] Timeout, retry, and idempotency behavior is explicit.
- [ ] Authentication/signature checks are validated.
- [ ] Consumer behavior under provider errors is tested.
- [ ] Provider-specific assumptions are documented with versions.

## Anti-patterns
- Embedding provider payload structures across business logic layers.
- Treating 2xx-only testing as sufficient integration coverage.
- Ignoring provider version drift and deprecations.

## Output
Hardened integration adapter plus contract and failure-mode evidence.
