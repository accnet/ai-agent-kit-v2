# OpenAI Skill — Best Practices

## API key and secret management

- Load `OPENAI_API_KEY` exclusively from environment variables or a secrets
  manager.  Never hard-code, commit, or log it.
- Use a dedicated service account key per environment (dev / staging / prod).
- Rotate keys on schedule and immediately on any suspected exposure.
- Restrict the key's permissions to only the models and endpoints the service
  needs (use project-scoped keys where the API supports it).

## Model and version pinning

- Pin the model name in a single config location (`OPENAI_MODEL=gpt-4o-mini`).
  Do not scatter model names across call sites.
- When upgrading a model, create a new prompt version, run evals, then switch.
  Treat model upgrades like dependency upgrades — one PR, evidence attached.
- Prefer dated model snapshots (e.g. `gpt-4o-2024-08-06`) in production to
  avoid silent behaviour changes from auto-updates.

## Request hygiene

- Always set `max_tokens` / `max_completion_tokens`.  An unbounded call can
  consume a large token budget silently.
- Set an explicit `timeout` on the client; 30 s is a reasonable default.
- Use `max_retries` ≥ 2 on the SDK client to handle transient 5xx and 429.
- Add `user` to every completion request to enable per-user rate-limit auditing
  on the OpenAI dashboard.

## Data privacy and PII

- Never send raw user PII (names, emails, health data) to the model unless
  the privacy review explicitly allows it.
- Log prompts only at DEBUG level, redacted, and never to persistent storage
  without explicit data-retention approval.
- Check the project's data-processing agreement with OpenAI before enabling
  training data opt-in/out defaults.

## Input validation

- Validate and sanitise user-supplied content before injecting into a prompt.
  Treat it the same as SQL input — escape, truncate to a known maximum, and
  strip control characters.
- Enforce a maximum prompt length (tokens or characters) before calling the API.
- Reject or strip content that matches known injection patterns (see `pitfalls.md`).

## Structured output

- Prefer `response_format=MyPydanticModel` (SDK ≥ 1.50) over `json_object`
  mode; you get validated, typed output instead of raw strings.
- Always have a fallback parse path: if `.parsed` is `None`, re-try once with
  a repair prompt, then raise a typed error that callers can catch.

## Testing

- Unit-test business logic by mocking the OpenAI client at the adapter
  boundary, not by mocking internal SDK methods.
- Use recorded fixtures (VCR / responses library) for integration tests.
- Gate real API calls behind an `OPENAI_INTEGRATION_TESTS=1` env flag.
- Assert on token usage in tests to catch prompt size regressions early.

## Observability and alerting

- Emit structured log lines (`request_id`, `model`, `prompt_tokens`,
  `completion_tokens`, `latency_ms`) for every call.
- Track cost per workflow; alert when daily spend exceeds budget.
- Trace multi-step chains (e.g. tool-call loops) with span IDs that correlate
  individual API calls to the originating user request.

## Prompt safety

- Run a content-policy check on model output before surfacing it to users when
  the task involves untrusted inputs.
- Log moderation results (flagged categories + scores) at WARN level.
- Do not blindly trust the model's self-reported confidence; validate
  structured output against your schema before use.

## Dependency management

- Check the OpenAI SDK changelog before upgrading; breaking changes in major
  versions (v0→v1→v2) require audit of every call site.
- Prefer `openai>=X.Y,<X+1` pinning over unconstrained `openai>=X.Y`.
- Run the full test suite (with recorded fixtures) after every SDK upgrade.
