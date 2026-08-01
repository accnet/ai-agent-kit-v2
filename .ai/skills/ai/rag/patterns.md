# RAG Patterns

## Ingestion pipeline
- Normalize source docs, deduplicate, and attach stable document/chunk ids.
- Store provenance metadata (source, version, timestamp, ACL scope).

## Retrieval pipeline
- Apply permission filters before semantic search.
- Use top-k retrieval plus optional lexical/hybrid reranking.
- Return citation payloads (doc_id, chunk_id, score, snippet).

## Freshness lifecycle
- Re-index on source updates, and tombstone deleted documents.
- Keep embedding model/version in index metadata.
