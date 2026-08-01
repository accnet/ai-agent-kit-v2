<<<<<<< HEAD
# PHP Backend Patterns

Follow the project's existing PSR standard (PSR-4 autoloading, PSR-7 HTTP messages, PSR-12 code style). Use dependency injection through the framework container; avoid `new` inside business logic. Return typed responses from controllers; validate and sanitize input at the boundary. Use named routes and service classes rather than fat controllers. Centralise environment config in `.env`/config files, never inline secrets.
=======
# PHP Patterns

- Keep controllers/thin entrypoints; move business rules into services.
- Use typed DTOs/value objects for cross-layer boundaries.
- Isolate infrastructure clients (DB/queue/http) behind interfaces.
- Prefer explicit transaction boundaries for multi-write workflows.
>>>>>>> origin/main
