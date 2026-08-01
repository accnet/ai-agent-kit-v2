# PostgreSQL Overview

PostgreSQL is a strongly-typed, ACID-compliant relational database with
first-class support for JSONB, arrays, full-text search, and extensions
(`pg_trgm`, `pgcrypto`, `postgis`, `pgvector`). Check the project's actual
server version (`SELECT version();`) before relying on version-gated
features — generated columns need 12+, `MERGE` needs 15+, and JSON
aggregation functions and JSONB path operators differ between major
versions.

Most correctness and performance problems in application code come from
three places: missing or wrong indexes, transactions held open longer than
necessary, and ORMs issuing N+1 queries. This reference focuses there
rather than on server administration (backup/replication/tuning), which
belongs to the project's ops runbook, not a task-scoped change.
