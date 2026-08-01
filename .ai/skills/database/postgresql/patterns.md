# PostgreSQL Patterns

- **Upsert via `ON CONFLICT`**: `INSERT ... ON CONFLICT (unique_col) DO
  UPDATE SET col = EXCLUDED.col` instead of a read-then-write
  check-then-insert, which races under concurrent writers.
- **Index selection by query shape**: default B-tree for equality/range on
  scalar columns; GIN for JSONB containment (`@>`) or array membership;
  GiST/`pg_trgm` for `ILIKE '%x%'` substring search; a partial index
  (`WHERE deleted_at IS NULL`) when most queries filter out the same rows.
- **`CREATE INDEX CONCURRENTLY`** for any index added to a table that
  already takes production writes — it doesn't take the exclusive lock a
  plain `CREATE INDEX` does, at the cost of not being usable inside a
  transaction block.
- **Explicit transaction boundaries.** Keep the transaction open only for
  the statements that must be atomic; do network calls, file I/O, or
  slow computation *before* `BEGIN` or after `COMMIT`, never inside it.
- **Read the plan before trusting a query.** `EXPLAIN (ANALYZE, BUFFERS)`
  on anything added to a hot path; a sequential scan on a table with more
  than a few thousand rows is a signal, not proof, of a missing index —
  confirm with the row counts the planner actually estimated vs. returned.
- **CTEs for readability, not as a query-boundary fence.** Since PG 12,
  non-recursive CTEs can be inlined by the planner like subqueries; don't
  assume `WITH x AS (...)` forces materialization — add `MATERIALIZED`
  explicitly if you need that guarantee.
- **Migrations as expand → migrate → contract** (see the `data-migration`
  core skill for the full discipline): add the new column nullable, backfill
  in batches, switch reads/writes over, only then add `NOT NULL`/drop the
  old column in a later release.
