# RAG Skill — Patterns

## 1. Ingestion pipeline

```
raw source → loader → cleaner → chunker → embedder → vector store
```

Keep each step as a pure function with a typed input and output so it can
be tested and swapped independently.

```python
# ingestion/pipeline.py
from dataclasses import dataclass

@dataclass
class RawDocument:
    id: str
    source_url: str
    text: str
    metadata: dict

@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    text: str
    metadata: dict         # includes source_url, page, section, tenant_id, etc.

def load(source: str) -> list[RawDocument]: ...
def clean(doc: RawDocument) -> RawDocument: ...
def chunk(doc: RawDocument, size: int = 512, overlap: int = 64) -> list[Chunk]: ...
def embed(chunks: list[Chunk], embedder) -> list[tuple[Chunk, list[float]]]: ...
def upsert(vectors: list[tuple[Chunk, list[float]]], store) -> None: ...
```

## 2. Chunking strategy

Select strategy based on content type:

| Content | Strategy |
|---|---|
| Prose / markdown | Recursive character splitter with semantic boundary detection |
| Code | Language-aware splitter (function / class boundaries) |
| Tables / structured | Row-level or JSON-record chunks |
| Long documents | Hierarchical: coarse (section) + fine (paragraph) chunks |

Always preserve metadata in each chunk:

```python
@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    text: str
    metadata: dict   # must include: source_url, section_title, page, tenant_id
```

Overlap of 10–20 % prevents sentences from being split across chunk boundaries.

## 3. Embedding model management

```python
# adapters/embedder.py
import os
from openai import OpenAI

EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}

def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    cleaned = [t.replace("\n", " ") for t in texts]
    response = client.embeddings.create(model=EMBED_MODEL, input=cleaned)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
```

Store the embedding model name alongside each vector in metadata.  When
the model changes, re-index the corpus rather than mixing embedding spaces.

## 4. Vector index lifecycle

```
create_index(name, dimension, metric="cosine")
upsert(vectors: list[{id, values, metadata}])
delete(ids: list[str])              # on document deletion
delete_by_filter(metadata_filter)   # on tenant/source removal
re_index(source)                    # full rebuild when embedding model changes
```

Use a versioned index name (`docs_v1`, `docs_v2`) when changing embedding
models so the old index remains live during migration.  Swap the read pointer
atomically after verifying the new index passes recall tests.

## 5. Metadata and access-control filtering

Every chunk must carry the tenant or access-group that owns it:

```python
metadata = {
    "tenant_id": tenant_id,      # mandatory for multi-tenant deployments
    "doc_id": doc.id,
    "source_url": doc.source_url,
    "section": section_title,
    "indexed_at": iso_timestamp,
}
```

At query time, always pass the caller's `tenant_id` as a metadata filter:

```python
results = store.query(
    vector=query_embedding,
    top_k=10,
    filter={"tenant_id": {"$eq": current_tenant_id}},
)
```

Never rely solely on the caller to supply the filter — enforce it server-side.

## 6. Retrieval: semantic + hybrid

**Semantic only (baseline):**

```python
query_vec = embed_batch(client, [query])[0]
results = store.query(vector=query_vec, top_k=top_k,
                      filter={"tenant_id": {"$eq": tenant_id}})
chunks = [r.metadata["text"] for r in results.matches]
```

**Hybrid (BM25 + dense, recommended for keyword-heavy queries):**

```python
# Most vector stores (Pinecone, Weaviate, Qdrant) support sparse+dense
sparse_vec = bm25_encode(query)
results = store.query(
    vector=query_vec, sparse_vector=sparse_vec,
    top_k=top_k, filter={"tenant_id": {"$eq": tenant_id}},
)
```

**Re-ranking (optional, reduces hallucination on diverse result sets):**

```python
from rerankers import Reranker

reranker = Reranker("cross-encoder/ms-marco-MiniLM-L-6-v2")
reranked = reranker.rank(query=query, docs=[r.metadata["text"] for r in results.matches])
chunks = [reranked.results[i].document.text for i in range(min(top_k, len(reranked.results)))]
```

## 7. Context assembly and citations

```python
def build_context(chunks: list[str], sources: list[str],
                  max_tokens: int = 2000) -> tuple[str, list[str]]:
    """Return (context_text, used_sources), truncated to max_tokens."""
    selected, used = [], []
    token_count = 0
    for chunk, source in zip(chunks, sources):
        tokens = count_tokens(chunk)
        if token_count + tokens > max_tokens:
            break
        selected.append(f"[{len(selected)+1}] {chunk}")
        used.append(source)
        token_count += tokens
    return "\n\n".join(selected), used
```

Include the citation list in the final prompt:

```python
system = (
    "Answer using only the provided context. "
    "Cite sources as [1], [2], etc."
)
user = f"Context:\n{context}\n\nQuestion: {question}"
```

## 8. Prompt-injection defence for retrieved content

Retrieved chunks are untrusted third-party content.  Apply before injection:

```python
import re

INJECTION_PATTERNS = [
    r"(?i)ignore (previous|all) instructions?",
    r"(?i)you are now",
    r"(?i)system prompt:",
    r"(?i)###\s*(instruction|system|prompt)",
]

def sanitise_chunk(text: str) -> str:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            return "[REDACTED: potential injection detected]"
    return text
```

Always place retrieved content in the `user` turn, never the `system` turn,
to limit the blast radius of any injection.

## 9. Freshness and incremental re-index

```python
def sync_document(doc: RawDocument, store, embedder) -> None:
    """Upsert if changed; skip if unchanged (compare hash)."""
    existing_hash = get_stored_hash(doc.id, store)
    new_hash = hashlib.sha256(doc.text.encode()).hexdigest()
    if existing_hash == new_hash:
        return
    chunks = chunk(clean(doc))
    vectors = embed(chunks, embedder)
    upsert(vectors, store)
    store_hash(doc.id, new_hash)

def delete_document(doc_id: str, store) -> None:
    store.delete_by_filter({"doc_id": {"$eq": doc_id}})
```

Schedule a reconciliation job that compares source document checksums against
the index and re-indexes or deletes stale entries.

## 10. Retrieval evaluation

Measure before shipping any retrieval change:

```python
# evaluation/recall_at_k.py
def recall_at_k(queries: list[dict], retrieve_fn, k: int) -> float:
    """queries: [{query, relevant_doc_ids}].  Returns mean recall@k."""
    scores = []
    for item in queries:
        results = retrieve_fn(item["query"], top_k=k)
        retrieved_ids = {r.metadata["doc_id"] for r in results.matches}
        relevant = set(item["relevant_doc_ids"])
        scores.append(len(retrieved_ids & relevant) / max(len(relevant), 1))
    return sum(scores) / len(scores) if scores else 0.0
```

Gate retrieval changes on recall@10 ≥ baseline.  Record results in the task
evidence file.
