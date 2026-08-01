<<<<<<< HEAD
# OpenAI Integration Evidence

Verification: a unit test mocks the OpenAI client and asserts the service returns a typed result; a test for the retry path confirms back-off on a mocked 429 response; `usage.total_tokens` is logged for each production call; structured output is validated against the declared JSON schema; no API key appears in committed files or logs.
=======
# OpenAI Examples

## Request checklist example
1. Identify existing OpenAI adapter module and config source.
2. Add/extend one typed method (input schema, model selection, timeout, retries).
3. Parse and validate output into domain DTO.
4. Emit metrics: request_count, latency_ms, input_tokens, output_tokens, error_type.
5. Add unit tests for success + provider failure + malformed output.

## Review evidence
- Changed adapter path(s)
- Tests proving output validation and retry behavior
- Log/trace snippet showing redaction and token accounting
>>>>>>> origin/main
