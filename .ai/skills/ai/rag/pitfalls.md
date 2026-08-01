# RAG Pitfalls

<<<<<<< HEAD
Do not inject unchecked retrieved chunks directly into prompts — a malicious document can redirect model behaviour (indirect prompt injection). Do not use overlapping chunks without tracking which source document a chunk belongs to, or citations will be wrong. Do not use a static `top_k` for all query types; tune per query category based on measured recall. Do not skip re-embedding after an embedding model upgrade — stale embeddings produce silently degraded results. Do not store sensitive personal data in the vector index without encryption and access-control policies. Do not ignore chunk boundary artefacts (split sentences, cut tables); review chunked output visually during pipeline development.
=======
- Reusing embeddings after changing tokenizer/model without re-indexing.
- Missing deletion workflow, leaving stale/forbidden chunks searchable.
- Skipping citations, making hallucinations impossible to audit.
- Letting retrieval bypass authorization filters.
- Prompt-injection instructions in retrieved chunks overriding system policy.
>>>>>>> origin/main
