# Prometheus Best Practices

- Use unit suffixes in metric names (`_seconds`, `_bytes`).
- Avoid unbounded labels (user ids, request ids).
- Pair alerts with runbook links and clear severity.
- Validate rule changes with promtool where available.
