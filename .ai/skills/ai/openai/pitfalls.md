# OpenAI Pitfalls

- Sending unbounded prompts or tool results (token spikes and latency blowups).
- Trusting model JSON without schema validation.
- Logging full prompts/responses containing credentials or customer data.
- Mixing business logic with provider payload wiring, making provider replacement hard.
- Silent retry loops without caps, causing duplicate writes and cost surprises.
