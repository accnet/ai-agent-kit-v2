# RAG Patterns

<<<<<<< HEAD
Split the pipeline into discrete stages: ingest → chunk → embed → index → retrieve → rerank → generate. Use fixed-size sliding-window chunking with overlap for dense text; use semantic/sentence-aware chunking for structured documents. Store document metadata (source, section, last-modified, access-control tags) alongside embeddings and filter on metadata before or after retrieval. Retrieve more candidates than needed (e.g. top-20) then rerank with a cross-encoder or LLM-as-judge before passing the top-k to the model. Cite sources in the generated response; include document ID and chunk offset so the reference can be verified. Use a dedicated embedding model version (e.g. `text-embedding-3-small`) pinned in config and re-embed the corpus when upgrading the model.
=======
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
>>>>>>> origin/main
