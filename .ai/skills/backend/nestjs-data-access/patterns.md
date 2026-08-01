# NestJS Data Access Patterns

- Put every ORM/query-builder call behind a repository or data-access provider; services
  depend on that interface, never on the ORM client directly.
- Own transaction boundaries in the service layer (`manager.transaction(...)` or
  `@Transactional()`), not in the controller and not spread across multiple repository
  calls that should be atomic.
- Every schema change ships as a migration with a working `down`; never rely on ORM
  auto-sync (`synchronize: true`) outside local development.
- Justify a new index with a query plan (`EXPLAIN ANALYZE`) captured against
  production-representative data volume, not intuition.
