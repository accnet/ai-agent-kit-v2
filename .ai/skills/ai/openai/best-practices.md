<<<<<<< HEAD
# OpenAI Integration Best Practices

Never hardcode API keys; load from environment variables and validate on startup. Set `temperature`, `max_tokens`, and `timeout` explicitly — do not rely on API defaults, which may change between model versions. Version-pin the `openai` package and the model name (e.g. `gpt-4o-2024-08-06`) to prevent silent behaviour changes. Log request IDs (`x-request-id`) and token usage (`usage.prompt_tokens`, `usage.completion_tokens`) for cost tracking and debugging; mask PII before logging prompts. Validate and sanitise model output before passing it to downstream systems. Write unit tests using a mock or stub for the API client; write integration tests against a fixed recorded response. Store prompt templates in versioned files or a prompt registry, not inline strings. Use the Batch API for non-real-time workloads to reduce cost by 50 %.
=======
# OpenAI Best Practices

- Verify the SDK and API mode already used in this repo before adding new endpoints.
- Pin model identifiers in config, not scattered literals.
- Separate user-visible errors from internal diagnostics; never expose raw provider traces.
- Track token usage and latency per operation and include correlation ids.
- Redact secrets and PII from prompts, logs, traces, and persisted transcripts.
- Add tests for: schema validation, retry branch, timeout branch, and provider error mapping.
>>>>>>> origin/main
