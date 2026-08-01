# OpenAI Patterns

## Adapter boundary
- Keep one provider client module responsible for auth, retries, timeouts, and model mapping.
- Pass typed request objects from application code; return typed response objects.

## Structured outputs
- Prefer schema-constrained outputs (JSON schema / strict parsing) for automation paths.
- Validate model output before persistence or side effects.

## Tool calling
- Whitelist callable tools and enforce argument validation.
- Record tool-call id and completion outcome for auditability.

## Resilience
- Use bounded retries with jitter for rate limits/transient network failures.
- Use idempotency keys for operations that can be replayed.
