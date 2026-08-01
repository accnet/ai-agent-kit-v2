# Redis Patterns

<<<<<<< HEAD
Organise keys with a consistent namespace prefix (e.g. `app:user:session:<id>`). Set an explicit TTL on every cache key; avoid keys that never expire. Use atomic operations (INCR, SETNX, MULTI/EXEC, Lua scripts) for counters and distributed locks. Use Redis Streams or Pub/Sub for event fan-out, not as a durable message queue unless persistence is enabled. For distributed locking prefer the Redlock algorithm or a dedicated library over plain SETNX. Separate databases or namespaces for cache, session, and queue data.
=======
- Namespace keys by domain and tenant/environment.
- Use TTLs deliberately and document cache invalidation triggers.
- Use atomic primitives (SET NX/XX, Lua, transactions) for contention-sensitive flows.
- Keep serialization format/version explicit for backward compatibility.
>>>>>>> origin/main
