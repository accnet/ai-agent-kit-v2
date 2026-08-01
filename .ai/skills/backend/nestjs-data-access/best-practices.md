# NestJS Data Access Best Practices

- Use parameterized queries everywhere; never interpolate a value into a raw SQL or
  query-builder string.
- Write a transaction test asserting that a failure mid-transaction rolls back every
  write, not just the one call that raised the error.
- Run migration `up` then `down` in CI against a disposable database, so a broken
  rollback is caught before it reaches a real environment.
- Manage the connection/pool lifecycle explicitly (a module's `onModuleDestroy`), so
  tests and app shutdown don't leak open connections.
