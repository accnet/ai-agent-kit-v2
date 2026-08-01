# OpenAI Skill — Pitfalls

## 1. API key leakage

**Problem:** `OPENAI_API_KEY` appears in logs, error messages, test fixtures,
or is committed to source control.

**How it happens:** String formatting that includes all env vars; exception
messages that include the request headers; copy-pasting a `.env` file.

**Prevention:** Never log `os.environ` wholesale.  Use a secrets scanner in
CI.  Rotate immediately if a key appears in any log.

---

## 2. Missing `max_tokens` allows runaway spend

**Problem:** A call without `max_tokens` can return thousands of tokens on a
verbose model, consuming budget silently.

**Prevention:** Always set `max_tokens` / `max_completion_tokens`.  Add a
cost-assertion test that fails if a call's token usage exceeds a threshold.

---

## 3. Prompt injection through user content

**Problem:** User-supplied text is injected directly into the system or user
prompt, allowing a user to override instructions.

```python
# DANGEROUS — user can terminate the task and inject new instructions
prompt = f"Summarise this document:\n{user_input}"
```

**Prevention:** Separate system instructions from user content structurally
(use the `messages` array correctly); validate and truncate user input; use
OpenAI's moderation endpoint for high-risk inputs.

---

## 4. Swallowing `openai.APIError` silently

**Problem:** Catching `Exception` broadly and returning an empty string hides
failures, making the system appear to work while producing no output.

**Prevention:** Catch specific exception types (`RateLimitError`,
`APIConnectionError`, `APIStatusError`) and propagate typed errors to callers.
Log and alert on unexpected exception types.

---

## 5. Hard-coded model names scattered across call sites

**Problem:** `gpt-4o-mini` is copied into 15 files.  When you need to upgrade
or A/B test, you must change 15 places and risk missing some.

**Prevention:** Centralise model names in config (`OPENAI_MODEL=gpt-4o-mini`
or a config dataclass).  All call sites read from one place.

---

## 6. No retry on rate limits causes cascade failures

**Problem:** On a `429 Too Many Requests`, the code raises immediately.  At
scale this causes a flood of failed requests rather than graceful degradation.

**Prevention:** Use the SDK's built-in `max_retries` and add application-level
exponential back-off for burst scenarios.  Expose a circuit-breaker metric.

---

## 7. Structured output fallback not handled

**Problem:** `response.choices[0].message.parsed` is `None` when the model
returns malformed JSON, and the code crashes with `AttributeError` or returns
`None` to callers unexpectedly.

**Prevention:** Always check `.parsed is not None`; implement a repair path
(re-prompt or default) and raise a typed error that callers can handle.

---

## 8. Streaming deltas not accumulated correctly

**Problem:** Printing each delta as received instead of accumulating leads to
partial tokens being treated as complete words.

**Prevention:** Collect all deltas into a list and join at the end.  For
structured streaming, use `stream.get_final_completion()` to get the assembled
message rather than assembling JSON fragments manually.

---

## 9. Unbounded token context crashes on long documents

**Problem:** Feeding a large document directly into the context window causes
a `BadRequestError: context window exceeded` at runtime.

**Prevention:** Count tokens with `tiktoken` before the API call; truncate or
chunk the document if it exceeds the model's context limit minus `max_tokens`.

---

## 10. Real API calls in unit tests

**Problem:** Unit tests that make live OpenAI calls are slow, non-deterministic,
cost money, and fail when the API is unavailable.

**Prevention:** Inject the client at the boundary; replace it with a mock or
use a `httpretty` / `respx` fixture in tests.  Gate live tests behind an
integration flag.

---

## 11. Copying SDK snippets without checking the version

**Problem:** Examples from documentation or Stack Overflow target a different
SDK major version (`openai<1` vs `openai>=1`).  The import paths, method names,
and exception hierarchy changed significantly.

**Prevention:** Check the pinned version first.  The v1 SDK uses
`openai.OpenAI()` and `openai.RateLimitError`; the v0 SDK uses
`openai.Completion.create()` and `openai.error.RateLimitError`.

---

## 12. Not logging `request_id` makes support debugging impossible

**Problem:** When a call returns unexpected output, OpenAI support needs the
`x-request-id` header value to look up the server-side trace.  If it is not
logged, you cannot reconstruct what happened.

**Prevention:** Log `response._request_id` at INFO level alongside token usage
for every call.
