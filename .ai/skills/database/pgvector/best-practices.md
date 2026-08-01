# pgvector Best Practices

- Ensure vector dimension constraints are enforced.
- Rebuild or dual-write indexes during embedding model migrations.
- Benchmark recall/latency before changing probe/list parameters.
- Keep ACL filters in SQL predicates before ranking.
