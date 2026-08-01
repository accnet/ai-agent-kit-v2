# RAG Skill — Overview

Use this skill when a task involves Retrieval-Augmented Generation: ingesting
documents into a vector store, retrieving relevant chunks, and injecting them
into a language model prompt.

## First steps before writing code

1. **Inspect the host project** — locate the existing embedding model, vector
   store adapter, and retrieval pipeline.  Check pinned versions for the
   embedding SDK, vector store client, and any orchestration framework
   (LangChain, LlamaIndex, Haystack).
2. **Understand the corpus** — what data sources feed the index?  How fresh
   must they be?  What access-control or tenant-isolation rules apply?
3. **Identify the retrieval contract** — what does a caller supply (query text,
   user ID, filters)?  What must be returned (chunks, scores, citations)?

## Scope of this skill

| Area | What this skill covers |
|---|---|
| Ingestion | Document loading, cleaning, normalisation |
| Chunking | Strategy selection, overlap, metadata preservation |
| Embeddings | Model selection, batching, normalisation, versioning |
| Vector index lifecycle | Create, upsert, update, delete, re-index |
| Metadata & access filtering | Per-tenant isolation, field filters |
| Retrieval | Semantic search, hybrid (BM25 + dense), re-ranking |
| Context assembly | Chunk ordering, deduplication, citation mapping |
| Prompt injection defence | Sanitising retrieved content before injection |
| Grounding & citations | Returning source references with model output |
| Freshness & reindex | Detecting stale docs, incremental updates, deletions |
| Evaluation | Recall@k, precision@k, answer faithfulness, RAGAS |
| Operational metrics | Latency, index size, embedding cost, retrieval quality |

## Related skills

- `openai` — for the LLM call that consumes the retrieved context.
- `api-contract` — when the retrieval result shape is part of an API surface.
- `security-review` — for access control, prompt injection, and PII in the corpus.
- `observability` — for retrieval latency, hit rate, and rerank distribution.
- `performance-profiling` — when retrieval latency is a bottleneck.
- `data-migration` — when re-indexing an existing corpus.

## Verification expectation

After any change to the RAG pipeline:

```
pytest -x tests/   # or project-specific runner
# Retrieval unit tests use a local or in-memory vector store
# Embedding calls are mocked in unit tests
# At least one recall@k integration test exists for the main query type
# No PII in logged chunk content
```
