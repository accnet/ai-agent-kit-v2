# OpenAI Skill — Patterns

## 1. Client initialisation

Wrap client creation in a single factory; never construct `OpenAI()` inline.

```python
# adapters/openai_client.py
import os
import httpx
from openai import OpenAI, AsyncOpenAI

def build_client(timeout: float = 30.0, max_retries: int = 3) -> OpenAI:
    """Return a configured synchronous OpenAI client.

    Reads OPENAI_API_KEY from the environment; raises early with a clear
    message rather than letting the SDK raise deep inside a call.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(
        api_key=api_key,
        timeout=httpx.Timeout(timeout, connect=5.0),
        max_retries=max_retries,
    )
```

For async code use `AsyncOpenAI` with the same pattern.

## 2. Chat completions

```python
def complete(client: OpenAI, messages: list[dict], model: str,
             max_tokens: int = 512) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
```

Always pass explicit `max_tokens` / `max_completion_tokens` to bound cost.

## 3. Structured output (JSON schema / Pydantic)

Use `response_format` with `json_schema` (SDK ≥ 1.50) or the `parse` helper:

```python
from pydantic import BaseModel

class Summary(BaseModel):
    title: str
    points: list[str]

# SDK ≥ 1.50 — typed parse
parsed = client.beta.chat.completions.parse(
    model=model,
    messages=messages,
    response_format=Summary,
)
result: Summary = parsed.choices[0].message.parsed
```

For older SDK versions fall back to `response_format={"type": "json_object"}`
and validate with Pydantic's `model_validate_json`.

## 4. Tool / function calling

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Return current temperature for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]

response = client.chat.completions.create(
    model=model, messages=messages, tools=tools, tool_choice="auto"
)

for choice in response.choices:
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            result = dispatch_tool(tc.function.name, tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
```

Keep tool dispatch in a plain dict/registry; avoid eval or dynamic import.

## 5. Streaming

```python
def stream_complete(client: OpenAI, messages: list[dict], model: str) -> str:
    collected: list[str] = []
    with client.chat.completions.stream(
        model=model, messages=messages, max_tokens=1024
    ) as stream:
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            collected.append(delta)
    return "".join(collected)
```

For partial JSON in structured streaming use `stream.get_final_completion()`.

## 6. Embeddings

```python
def embed(client: OpenAI, texts: list[str],
          model: str = "text-embedding-3-small") -> list[list[float]]:
    # Batch up to 2048 items per request; strip newlines as per OpenAI docs.
    cleaned = [t.replace("\n", " ") for t in texts]
    response = client.embeddings.create(model=model, input=cleaned)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
```

## 7. Retry and rate-limit handling

The SDK retries `429` and `5xx` automatically when `max_retries > 0`.  For
application-level retry with custom back-off:

```python
import time
from openai import RateLimitError, APIStatusError

def complete_with_backoff(client, messages, model, max_attempts=5):
    for attempt in range(max_attempts):
        try:
            return complete(client, messages, model)
        except RateLimitError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(2 ** attempt)
```

## 8. Observability

Log request ID and token usage at INFO level for every non-streaming call:

```python
import logging
log = logging.getLogger(__name__)

response = client.chat.completions.create(...)
log.info(
    "openai.chat",
    extra={
        "request_id": response._request_id,      # header: x-request-id
        "model": response.model,
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    },
)
```

For streaming, use `stream.get_final_completion().usage` after the loop.

## 9. Prompt management

Keep prompt text in versioned files, not inline strings:

```
prompts/
  summarise_v1.txt      # stable, shipped
  summarise_v2.txt      # under test
```

Load with a registry that maps task → (file, model, params):

```python
PROMPTS = {
    "summarise": {"file": "prompts/summarise_v1.txt", "model": "gpt-4o-mini",
                  "max_tokens": 256},
}

def load_prompt(name: str, **vars) -> str:
    cfg = PROMPTS[name]
    template = Path(cfg["file"]).read_text()
    return template.format(**vars)
```

Changing a prompt is a versioned artefact change; treat it like a schema
migration — keep the old version until the new one has been evaluated.

## 10. Token and cost budgets

- Set `max_tokens` / `max_completion_tokens` on every call.
- Track `response.usage.total_tokens` per request and aggregate per workflow.
- Alert when a single call exceeds a configured threshold (e.g. 8 000 tokens).
- For long documents, count tokens before the call using `tiktoken`:

```python
import tiktoken

def count_tokens(text: str, model: str) -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))
```
