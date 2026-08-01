# Prometheus Pitfalls

- High-cardinality labels causing memory pressure.
- Alert storms from missing `for` durations and grouping.
- Missing histogram buckets for latency distributions.
- Silent scrape target failures from stale config.
