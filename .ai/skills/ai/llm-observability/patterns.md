# LLM Observability Patterns

- Emit one trace/span per inference step with correlation id.
- Capture model, prompt version, latency, token usage, and outcome class.
- Aggregate per-feature dashboards for p50/p95 latency, error rate, and token spend.
- Record redacted sample payloads only where policy allows.
