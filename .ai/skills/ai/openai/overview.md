# OpenAI Overview

Use this skill when a task integrates OpenAI APIs (Responses, Chat Completions, embeddings, image/audio generation, or tool calling).

Before editing code, inspect the project adapter and pinned SDK/model versions first. Keep provider calls isolated behind the existing adapter boundary and avoid leaking provider-specific payload shapes into business logic.

For every change, define: expected inputs, structured output schema, timeout/retry policy, logging redaction, and fallback behavior when OpenAI is unavailable.
