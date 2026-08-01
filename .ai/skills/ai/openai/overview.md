<<<<<<< HEAD
# OpenAI Integration

Use when a task integrates with the OpenAI API (Chat Completions, Responses API, Embeddings, Fine-tuning, Batch, or Assistants). Inspect the project's pinned `openai` client version, model names in use (check config/environment), prompt templates, and existing API call patterns before making changes.
=======
# OpenAI Overview

Use this skill when a task integrates OpenAI APIs (Responses, Chat Completions, embeddings, image/audio generation, or tool calling).

Before editing code, inspect the project adapter and pinned SDK/model versions first. Keep provider calls isolated behind the existing adapter boundary and avoid leaking provider-specific payload shapes into business logic.

For every change, define: expected inputs, structured output schema, timeout/retry policy, logging redaction, and fallback behavior when OpenAI is unavailable.
>>>>>>> origin/main
