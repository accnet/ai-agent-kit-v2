# Redis Evidence

Verification: integration test sets a key with TTL and reads it back before expiry; after TTL elapses the key is absent; a lock acquisition test confirms only one concurrent caller holds the lock; `redis-cli INFO memory` shows `used_memory_human` is within configured `maxmemory`.
