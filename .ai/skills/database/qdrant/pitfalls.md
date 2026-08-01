# Qdrant Pitfalls

- Inconsistent vector dimensions across upserts.
- Querying without payload security filters.
- Large rebuilds with no throttling/backpressure controls.
- Ignoring replica/shard settings for HA requirements.
