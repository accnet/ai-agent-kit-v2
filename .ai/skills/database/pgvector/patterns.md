# pgvector Patterns

- Store vector, model version, and source metadata together.
- Use appropriate operator (`<->`, `<=>`, `<#>`) per distance metric.
- Choose index type (`ivfflat`/`hnsw`) based on dataset size and latency target.
- Run hybrid retrieval via SQL (vector + lexical filters).
