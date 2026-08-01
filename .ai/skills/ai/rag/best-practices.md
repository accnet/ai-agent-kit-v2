# RAG Best Practices

- Choose chunk size/overlap from measured retrieval quality, not intuition.
- Enforce tenant/user ACL filters at query time and evaluation time.
- Evaluate recall@k and answer faithfulness on a fixed benchmark set.
- Treat retrieved text as untrusted input; sanitize before prompt assembly.
- Cap context window budget and prefer reranking over blindly increasing k.
