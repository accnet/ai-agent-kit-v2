# Redis Pitfalls

<<<<<<< HEAD
Do not use Redis as a primary durable data store without explicit persistence configuration and a backup strategy. Do not store large blobs (>1 MB) in Redis; it degrades throughput for all clients sharing the instance. Do not use KEYS/SMEMBERS on production with millions of entries; prefer SCAN with a cursor. Do not ignore connection pool exhaustion; set pool size and timeout explicitly. Do not rely on key expiration for security-critical invalidation — clients may hold stale data for up to the TTL.
=======
- Unbounded key cardinality from user-generated key components.
- Missing TTLs leading to memory pressure and eviction of critical keys.
- Assuming in-memory writes are durable enough for source-of-truth data.
- Non-atomic read-modify-write race conditions.
>>>>>>> origin/main
