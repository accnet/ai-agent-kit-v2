# PostgreSQL Best Practices

- Use `timestamptz`, never bare `timestamp`, for anything that records a
  point in time — `timestamp` silently drops timezone info and drifts once
  the app or DB server's local timezone differs.
- Add `NOT NULL` and an explicit default wherever the column has no
  legitimate "unset" state; let the schema, not application code, be the
  source of truth for required fields.
- Index every foreign-key column explicitly — Postgres does not do this
  automatically, and its absence turns child-row deletes/updates into full
  table scans for the FK check.
- Enforce invariants the app already assumes (`UNIQUE`, `CHECK`,
  `REFERENCES ... ON DELETE`) at the schema level as a second layer behind
  application validation, not instead of it.
- Size the connection pool to the server's real capacity
  (`max_connections`), and share one pool per process, not one per request
  — connection setup is the most common source of latency spikes under
  load.
- Avoid `SELECT *` in application code paths that get maintained over
  time; an added column silently changes the shape of every caller that
  destructures the result.
- Batch large backfills/deletes (e.g. `LIMIT 5000` per iteration with a
  short pause) instead of one unbounded statement — an unbounded write on
  a large table holds its locks for the statement's full duration and can
  stall autovacuum and other writers.
- Don't store large blobs (images, PDFs, generated exports) as column data;
  put them in object storage and store the reference — large row payloads
  bloat the table and slow every sequential scan.
