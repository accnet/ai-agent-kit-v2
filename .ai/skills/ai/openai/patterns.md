<<<<<<< HEAD
# OpenAI Integration Patterns

Encapsulate all OpenAI API calls in a dedicated service or adapter class; do not scatter `client.chat.completions.create()` calls across the codebase. Use structured output (`response_format: {type: "json_schema", json_schema: {...}}`) when the downstream code parses the model's response — avoid free-form JSON parsing with string matching. For tool/function calling, define a typed schema for each tool and validate the returned tool arguments before execution. Implement exponential backoff with jitter for rate-limit (429) and transient server errors (5xx). Stream responses with `stream: true` only when the UX requires incremental output; use non-streaming for structured output to simplify parsing. Manage token budget explicitly: count tokens with `tiktoken` (or the API's usage field) and truncate or summarise context before the model's context limit.
=======
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
>>>>>>> origin/main
