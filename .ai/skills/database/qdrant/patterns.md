# Qdrant Patterns

- Define collection with explicit vector size and distance metric.
- Store payload metadata for tenant/ACL filtering.
- Use batch upserts for ingestion and idempotent document ids.
- Separate online query collections from bulk rebuild workflows.
