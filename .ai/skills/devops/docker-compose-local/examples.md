# Docker Compose Local Evidence

```yaml
services:
  api:
    build: .
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    ports: ["3000:3000"]
  db:
    image: postgres:16.2
    environment:
      POSTGRES_PASSWORD: local-only
    volumes: ["postgres_data:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5
volumes:
  postgres_data:
```

Evidence: a clean `docker compose up` from a fresh clone, all services reporting healthy,
an integration smoke test against the running stack, and the documented reset/teardown
command actually run once to confirm it works.
