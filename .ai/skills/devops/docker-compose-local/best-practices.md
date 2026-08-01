# Docker Compose Local Best Practices

- Provide one bootstrap command (`docker compose up -d`, or a `make dev`) that gets a new
  contributor to a running stack without prior knowledge.
- Pin image versions (`postgres:16.2`, not `postgres:latest`) so local environments stay
  reproducible across the team and over time.
- Document the reset/seed path explicitly (`docker compose down -v && docker compose up
  -d && npm run seed`) rather than leaving it to be rediscovered.
- Use Compose `profiles` for optional services (a mail-catcher, an admin UI) so the
  default `up` stays fast and minimal.
