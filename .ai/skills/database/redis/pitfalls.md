# Redis Pitfalls

Do not use Redis as a primary durable data store without explicit persistence configuration and a backup strategy. Do not store large blobs (>1 MB) in Redis; it degrades throughput for all clients sharing the instance. Do not use KEYS/SMEMBERS on production with millions of entries; prefer SCAN with a cursor. Do not ignore connection pool exhaustion; set pool size and timeout explicitly. Do not rely on key expiration for security-critical invalidation — clients may hold stale data for up to the TTL.
