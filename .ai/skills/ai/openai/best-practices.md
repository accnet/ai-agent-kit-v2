# OpenAI Best Practices

- Verify the SDK and API mode already used in this repo before adding new endpoints.
- Pin model identifiers in config, not scattered literals.
- Separate user-visible errors from internal diagnostics; never expose raw provider traces.
- Track token usage and latency per operation and include correlation ids.
- Redact secrets and PII from prompts, logs, traces, and persisted transcripts.
- Add tests for: schema validation, retry branch, timeout branch, and provider error mapping.
