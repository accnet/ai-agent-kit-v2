<<<<<<< HEAD
# MySQL Evidence

Verification: new migration runs cleanly on a fresh schema (`migrate up` exits 0), `EXPLAIN SELECT ...` shows index usage, integration test inserts and retrieves a record correctly, and the slow-query log shows no full-table scans introduced by the change.
=======
# MySQL Examples

- Migration sequence: add nullable column -> batch backfill -> add index -> enforce NOT NULL.
- Validation evidence: migration dry-run output + explain plan before/after + targeted test.
>>>>>>> origin/main
