# OpenAI Skill — Examples

These examples show representative patterns for the most common tasks.
Before using them, verify that the host project's SDK version and adapter
style match; adapt naming and imports to what already exists.

---

## Example 1: Basic chat completion with error handling

```python
# adapters/openai_client.py
import logging
import os
import time

import httpx
from openai import APIStatusError, OpenAI, RateLimitError

log = logging.getLogger(__name__)


def build_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(
        api_key=api_key,
        timeout=httpx.Timeout(30.0, connect=5.0),
        max_retries=3,
    )


def chat(client: OpenAI, messages: list[dict], model: str,
         max_tokens: int = 512) -> str:
    start = time.monotonic()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    log.info(
        "openai.chat",
        extra={
            "request_id": response._request_id,
            "model": response.model,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "latency_ms": latency_ms,
        },
    )
    return response.choices[0].message.content or ""
```

**Unit test:**

```python
# tests/test_openai_adapter.py
from unittest.mock import MagicMock, patch
import pytest
from adapters.openai_client import chat


@pytest.fixture
def mock_client():
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "Hello, world!"
    response = MagicMock()
    response.choices = [choice]
    response.model = "gpt-4o-mini"
    response.usage.prompt_tokens = 10
    response.usage.completion_tokens = 5
    response._request_id = "req-abc123"
    client.chat.completions.create.return_value = response
    return client


def test_chat_returns_content(mock_client):
    result = chat(mock_client, [{"role": "user", "content": "Hi"}],
                  model="gpt-4o-mini")
    assert result == "Hello, world!"


def test_chat_calls_create_with_max_tokens(mock_client):
    chat(mock_client, [], model="gpt-4o-mini", max_tokens=128)
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 128
```

---

## Example 2: Structured output with Pydantic (SDK ≥ 1.50)

```python
# services/summariser.py
from pydantic import BaseModel
from openai import OpenAI


class DocumentSummary(BaseModel):
    title: str
    key_points: list[str]
    word_count_estimate: int


def summarise(client: OpenAI, text: str, model: str) -> DocumentSummary:
    parsed = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "Extract a structured summary."},
            {"role": "user", "content": text[:8000]},   # guard context window
        ],
        response_format=DocumentSummary,
        max_tokens=512,
    )
    result = parsed.choices[0].message.parsed
    if result is None:
        raise ValueError("Model returned unparseable structured output")
    return result
```

**Verification:** `result` is a typed `DocumentSummary`; no manual JSON
parsing needed.  The test stubs `.parsed` on the mock to return a known
`DocumentSummary` instance.

---

## Example 3: Tool calling with a dispatch registry

```python
# services/tool_agent.py
import json
from openai import OpenAI

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search the internal knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
]

def _dispatch(name: str, arguments: str) -> str:
    args = json.loads(arguments)
    if name == "search_docs":
        return search_docs(args["query"])     # project-local function
    raise ValueError(f"Unknown tool: {name}")


def run_agent(client: OpenAI, user_query: str, model: str) -> str:
    messages = [{"role": "user", "content": user_query}]
    for _ in range(5):     # max iterations guard
        response = client.chat.completions.create(
            model=model, messages=messages, tools=TOOLS,
            tool_choice="auto", max_tokens=1024,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""
        messages.append(msg)
        for tc in msg.tool_calls:
            result = _dispatch(tc.function.name, tc.function.arguments)
            messages.append({
                "role": "tool", "tool_call_id": tc.id, "content": result,
            })
    return ""   # max iterations exceeded
```

---

## Example 4: Streaming completion

```python
# services/stream_chat.py
from collections.abc import Iterator
from openai import OpenAI


def stream_chat(client: OpenAI, prompt: str, model: str) -> Iterator[str]:
    """Yield text deltas as they arrive."""
    with client.chat.completions.stream(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    ) as stream:
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
```

Server-sent-events endpoint (FastAPI):

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.get("/stream")
def stream(prompt: str):
    def generate():
        for delta in stream_chat(client, prompt, model="gpt-4o-mini"):
            yield f"data: {delta}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## Example 5: Embeddings with batching

```python
# services/embedder.py
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-small"
BATCH_SIZE = 512


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Return one embedding vector per input text."""
    cleaned = [t.replace("\n", " ") for t in texts]
    results: list[list[float]] = []
    for i in range(0, len(cleaned), BATCH_SIZE):
        batch = cleaned[i : i + BATCH_SIZE]
        response = client.embeddings.create(model=EMBED_MODEL, input=batch)
        batch_vectors = [
            item.embedding
            for item in sorted(response.data, key=lambda x: x.index)
        ]
        results.extend(batch_vectors)
    return results
```

**Verification:** `len(results) == len(texts)`.  Each vector has dimension
1536 (small) or 3072 (large).  Test with a batch of 2 items and assert lengths.

---

## Example 6: Token budget guard

```python
# utils/token_guard.py
import tiktoken

def check_token_budget(text: str, model: str, max_prompt_tokens: int) -> str:
    """Truncate text to fit within the token budget; return truncated text."""
    enc = tiktoken.encoding_for_model(model)
    tokens = enc.encode(text)
    if len(tokens) > max_prompt_tokens:
        tokens = tokens[:max_prompt_tokens]
        text = enc.decode(tokens)
    return text
```

Usage before any API call that injects user content:

```python
safe_text = check_token_budget(user_content, model=model, max_prompt_tokens=3000)
```
