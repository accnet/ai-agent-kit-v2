# OpenAI Skill — Overview

Use this skill when a task involves calling the OpenAI API (chat completions,
Responses API, embeddings, function/tool calling, structured outputs, or
streaming). Load it alongside the role-specific core skills; do not replace
project conventions with generic snippets.

## First steps before writing code

1. **Inspect the host project** — locate the existing OpenAI client initialisation,
   check the pinned SDK version (`openai` in `requirements.txt`, `pyproject.toml`,
   or `package.json`), and read how secrets are loaded (env var, secrets manager,
   vault).  Never guess; every project has its own adapter layer.
2. **Identify the API surface in use** — the project may use the classic
   `chat/completions` endpoint, the newer Responses API, or a higher-level
   framework (LangChain, LlamaIndex, Instructor).  Match the style already present.
3. **Confirm the model names and versions** — model names evolve (`gpt-4o`,
   `gpt-4o-mini`, `o1`, `o3`).  Read the project's model configuration before
   hard-coding any name.

## Scope of this skill

| Area | What this skill covers |
|---|---|
| Client / API boundary | Initialisation, auth, base URL overrides, timeout/retry config |
| Completions & Responses API | Chat completions, the newer `responses.create` surface |
| Structured outputs | JSON mode, `response_format`, Pydantic/schema-based parsing |
| Tool / function calling | Tool definitions, parallel calls, result injection |
| Streaming | `stream=True`, delta accumulation, partial JSON handling |
| Embeddings | `embeddings.create`, batching, normalisation |
| Retries & rate limits | Exponential back-off, `RateLimitError`, `APIStatusError` |
| Secrets & data privacy | API key handling, PII scrubbing, logging policy |
| Observability | Request IDs, token counts, latency traces |
| Testing & mocking | Deterministic unit tests without real API calls |
| Prompt versioning | Prompt files, variable injection, change tracking |
| Token / cost budgets | `max_tokens`, `max_completion_tokens`, usage accounting |

## Related skills

- `api-contract` — when changing an API boundary that exposes LLM output to callers.
- `observability` — for tracing and alerting on LLM latency/cost.
- `security-review` — when handling untrusted user content or sensitive data.
- `integration-contracts` — when the OpenAI API is a critical external dependency.
- `performance-profiling` — when latency or cost SLOs are in scope.
- `rag` — when completions are augmented with retrieved context.

## Verification expectation

After any change touching the OpenAI integration:

```
pytest -x tests/   # or project-specific runner
# No real API calls in unit tests (mock/stub must be used)
# Token usage logged at INFO level for every non-streaming call
# API key must not appear in logs, traces, or test fixtures
```
