# PHP Patterns

- Keep controllers/thin entrypoints; move business rules into services.
- Use typed DTOs/value objects for cross-layer boundaries.
- Isolate infrastructure clients (DB/queue/http) behind interfaces.
- Prefer explicit transaction boundaries for multi-write workflows.
