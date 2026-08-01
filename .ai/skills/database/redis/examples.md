<<<<<<< HEAD
# Redis Evidence

Verification: integration test sets a key with TTL and reads it back before expiry; after TTL elapses the key is absent; a lock acquisition test confirms only one concurrent caller holds the lock; `redis-cli INFO memory` shows `used_memory_human` is within configured `maxmemory`.
=======
# Redis Examples

- Cache-aside read path with TTL and explicit invalidation on write.
- Distributed lock pattern with lease timeout and safe release token.
- Evidence: metrics snapshot + race-condition test.
>>>>>>> origin/main
