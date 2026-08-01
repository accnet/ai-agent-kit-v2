# RAG Pitfalls

- Reusing embeddings after changing tokenizer/model without re-indexing.
- Missing deletion workflow, leaving stale/forbidden chunks searchable.
- Skipping citations, making hallucinations impossible to audit.
- Letting retrieval bypass authorization filters.
- Prompt-injection instructions in retrieved chunks overriding system policy.
