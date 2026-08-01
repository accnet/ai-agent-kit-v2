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
