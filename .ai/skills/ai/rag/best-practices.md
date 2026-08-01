# RAG Skill — Best Practices

## Corpus ingestion

- **Normalise before chunking** — strip HTML tags, normalise Unicode, remove
  boilerplate headers/footers so tokens are spent on signal, not noise.
- **Preserve provenance** — every chunk must carry `doc_id`, `source_url`,
  `section_title`, and `indexed_at`.  Without provenance you cannot produce
  citations or debug stale results.
- **Hash-based deduplication** — compute a SHA-256 of the cleaned document text
  before ingestion; skip unchanged documents to avoid wasted embedding calls.
- **Idempotent upserts** — ingestion must be safe to re-run; use the document ID
  as the vector ID so repeated runs overwrite rather than duplicate.

## Chunking

- **Match chunk size to the model's context window** — for `gpt-4o` (128k)
  you can afford larger chunks (1 000–2 000 tokens); for smaller windows keep
  chunks at 256–512 tokens.
- **Use overlap** — 10–20 % overlap prevents sentences being split across
  boundaries and losing context.
- **Respect structural boundaries** — split on paragraph / heading / sentence
  rather than hard character counts to preserve coherence.
- **Test chunk quality** — spot-check that meaningful sentences are never
  truncated mid-word; add a unit test that verifies chunk boundaries for a
  known fixture document.

## Embedding model

- **Pin the model name** in a single config location (`EMBED_MODEL=text-embedding-3-small`).
- **Never mix embedding spaces** — if you change the model, re-index the entire
  corpus before querying.  Use versioned index names during migration.
- **Normalise vectors** — cosine similarity is the standard metric; most
  client libraries return already-normalised vectors but verify for your store.
- **Batch embed** — send up to 512–2 048 texts per API call to amortise
  round-trip cost; respect per-minute token limits.

## Vector store and index

- **Define a schema/mapping** for metadata fields up front; adding fields to an
  existing dense index is often destructive.
- **Version your index** (`docs_v1`, `docs_v2`) to allow zero-downtime
  migration: build the new index in parallel, validate, then swap the read
  pointer.
- **Set metadata index fields** explicitly in your store for any field you
  filter on at query time; unindexed filters may cause full scans or silently
  return wrong results.
- **Monitor index size** and set an alert when it approaches store capacity.

## Retrieval

- **Always pass access-control filters** at query time; do not rely on the
  caller to do this.  Enforce tenant isolation server-side.
- **Use hybrid retrieval** (sparse + dense) for keyword-heavy domains; pure
  semantic search underperforms on exact-match queries (product codes, names).
- **Apply a minimum score threshold** — discard results below 0.70 cosine
  similarity to avoid injecting irrelevant context.
- **Re-rank before assembling context** for diverse result sets; cross-encoder
  re-ranking typically improves faithfulness at the cost of a few ms.

## Context assembly

- **Respect the token budget** — count tokens before assembling context; leave
  enough headroom for the system prompt and expected completion.
- **Order chunks by relevance** (highest score first) and remove near-duplicates
  (cosine sim > 0.95).
- **Include citations** in the assembled context so the model can reference them;
  verify the model returns citation markers that map to real sources.

## Prompt-injection defence

- **Sanitise retrieved content** — scan for injection patterns before inserting
  chunks into the prompt.
- **Isolate retrieved content in the `user` turn** — never inject it into the
  `system` turn where it has higher authority.
- **Limit chunk authority** — frame the system prompt to say "answer only from
  the provided context" rather than allowing the model to mix external knowledge
  with retrieved content.

## Freshness and deletion

- **Schedule a reconciliation job** — compare source document checksums against
  the index on a regular cadence (e.g. hourly / nightly) to catch stale content.
- **Delete on source deletion** — when a source document is removed, delete all
  its chunks from the vector store immediately to avoid serving stale answers.
- **Re-index on bulk changes** — when the chunking strategy or embedding model
  changes, rebuild the entire index; partial updates across different strategies
  corrupt retrieval quality.

## Evaluation and quality gates

- **Measure recall@k before shipping** — compare against a baseline on a fixed
  evaluation set; reject changes that reduce recall.
- **Measure faithfulness** — use an LLM judge or RAGAS to check that answers
  are grounded in the retrieved context, not hallucinated.
- **Record evaluation results** as task evidence; include the evaluation set
  size, recall@5, recall@10, and faithfulness score.
- **Re-evaluate after any change** to chunking, embedding model, retrieval
  parameters, or re-ranking.

## Operations and observability

- Emit per-query metrics: `retrieval_latency_ms`, `chunks_returned`,
  `min_score`, `max_score`, `embedding_tokens_used`.
- Alert on: retrieval latency > 2 s; recall@10 drop > 5 pp vs baseline;
  index size growing faster than expected.
- Log `doc_id` and `chunk_index` for every retrieved chunk so you can
  reproduce any answer in support investigations.
