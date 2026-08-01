# Embeddings Pitfalls

- Mixing vectors from different models in one index without version filters.
- Ignoring unicode normalization/language preprocessing drift.
- Re-embedding entire corpora unnecessarily for tiny source edits.
- Storing vectors without source linkage for traceability.
