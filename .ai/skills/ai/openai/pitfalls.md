<<<<<<< HEAD
# OpenAI Integration Pitfalls

Do not trust model output as safe input for SQL queries, shell commands, or HTML rendering without validation and sanitisation — prompt injection is a real attack vector. Do not swallow `openai.APIError` exceptions silently; surface them as structured errors with the request ID. Do not call the API synchronously from a synchronous web worker thread without a timeout; enforce a hard deadline. Do not use `max_tokens` values far below what the model needs to complete a response — it silently truncates output, which breaks JSON parsing. Do not log raw prompts containing PII in plaintext log sinks. Do not assume a model update (e.g. gpt-4o → gpt-4o-2024-11-20) has identical output behaviour; test before upgrading.
=======
# OpenAI Pitfalls

- Sending unbounded prompts or tool results (token spikes and latency blowups).
- Trusting model JSON without schema validation.
- Logging full prompts/responses containing credentials or customer data.
- Mixing business logic with provider payload wiring, making provider replacement hard.
- Silent retry loops without caps, causing duplicate writes and cost surprises.
>>>>>>> origin/main
