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
Implement webhook/event processing that is authentic, idempotent, and retry-safe.

## When to use
Inbound webhooks, event consumers, async callbacks, or retrying external side effects.

## Procedure
1. Validate webhook authenticity (signature, timestamp, source constraints).
2. Design idempotency key strategy and deduplication storage semantics.
3. Implement retry policy with bounded attempts and backoff/jitter.
4. Handle out-of-order or duplicate deliveries safely.
5. Expose observability for delivery status, retry counts, and dead-letter outcomes.

## Checklist
- [ ] Signature/auth checks are enforced and tested.
- [ ] Idempotency prevents duplicate side effects.
- [ ] Retry policy is bounded and documented.
- [ ] Poison/failing events have dead-letter handling.
- [ ] Operational metrics/alerts exist for failure spikes.

## Anti-patterns
- Processing webhook payloads without signature verification.
- Non-idempotent handlers retried blindly.
- Infinite retries with no dead-letter path.

## Output
Reliable webhook/event handler with idempotency and retry evidence.
