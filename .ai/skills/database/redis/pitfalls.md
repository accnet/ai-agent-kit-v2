# Redis Pitfalls

- Unbounded key cardinality from user-generated key components.
- Missing TTLs leading to memory pressure and eviction of critical keys.
- Assuming in-memory writes are durable enough for source-of-truth data.
- Non-atomic read-modify-write race conditions.
