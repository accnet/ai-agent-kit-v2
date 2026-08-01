# Docker Compose Local Patterns

- Declare service readiness with `healthcheck:` and gate dependents with
  `depends_on: { condition: service_healthy }` — plain `depends_on` only waits for the
  container to start, not for the app inside it to be ready.
- Use named volumes for stateful services (`postgres_data:`) so `docker compose down`
  doesn't silently discard data unless `-v` is passed explicitly.
- Keep local secrets in a git-ignored `.env` (with a committed `.env.example`), never
  inline in `docker-compose.yml`.
- Expose only the ports a developer actually needs on the host; keep inter-service
  traffic on the compose network by service name.
