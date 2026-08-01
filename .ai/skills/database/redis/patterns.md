# Redis Patterns

- Namespace keys by domain and tenant/environment.
- Use TTLs deliberately and document cache invalidation triggers.
- Use atomic primitives (SET NX/XX, Lua, transactions) for contention-sensitive flows.
- Keep serialization format/version explicit for backward compatibility.
