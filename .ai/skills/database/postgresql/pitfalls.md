# PostgreSQL Pitfalls

- **N+1 queries from an ORM.** A list endpoint that lazily loads a related
  row per item turns one page load into hundreds of round-trips; use
  eager loading (`JOIN`/`.includes`/`.select_related` — whatever the
  project's ORM calls it) for anything rendered in a loop.
- **Implicit type mismatch defeats the index.** Comparing a `text` column
  to an integer literal, or an untyped parameter to a `uuid`/`timestamptz`
  column, can force a cast that makes the planner skip the index entirely
  — check `EXPLAIN` for a sequential scan you didn't expect.
- **`CREATE INDEX` (without `CONCURRENTLY`) on a live table** takes an
  exclusive lock that blocks writes for the build's full duration — fine
  on an empty migration/dev table, an outage risk on a populated
  production one.
- **`ALTER TABLE ... ADD COLUMN ... DEFAULT <non-null literal>`** on
  older Postgres (< 11) rewrites the whole table; even on 11+, adding a
  volatile default or a new `NOT NULL` constraint without a default can
  still take a long-held lock — test the migration's actual lock duration
  against a production-sized copy, not an empty dev database.
- **Long-running transactions block autovacuum** on the tables they touch
  (and, past a threshold, on the whole database via the transaction ID
  wraparound horizon) — a forgotten open transaction in a debugger session
  or a batch job that never commits is a common, hard-to-spot cause of
  "queries got slow for no reason."
- **Unbounded `IN (...)` lists** built from an unpaginated upstream result
  set silently degrade from fast to unusable as the list grows — bound the
  batch size or convert to a join against a temp table/values list.
- **`LIKE '%term%'`** without a trigram (`pg_trgm`) or full-text index
  cannot use a plain B-tree and falls back to a sequential scan regardless
  of table size.
- **Connection exhaustion from unpooled connections**, especially in
  serverless/lambda-style deployments that open a new connection per
  invocation — use a pooler (PgBouncer) or the platform's pooled driver.
