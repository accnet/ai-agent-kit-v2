# MySQL Best Practices

- Run migrations with lock-awareness on large tables.
- Backfill in batches to avoid long-running locks.
- Keep charset/collation consistent with existing schema defaults.
- Add tests for schema contract and query behavior changes.
