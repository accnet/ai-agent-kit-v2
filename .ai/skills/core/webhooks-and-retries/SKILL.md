---
name: webhooks-and-retries
description: Implement signed, idempotent webhooks and retry-safe external side effects.
version: 2.0.0
tier: core
stack: [any]
owner: integration
gates: [G2, G3]
related: []
---

# Skill: webhooks-and-retries

## Purpose
Implement signed, idempotent webhooks and retry-safe external side effects.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Verify signatures before parsing business data. Persist idempotency keys, classify retryable failures, use bounded backoff, and expose dead-letter or recovery handling.

## Checklist
- [ ] Signature verification is tested
- [ ] Duplicate delivery is harmless
- [ ] Retries are bounded
- [ ] Recovery path is documented

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
