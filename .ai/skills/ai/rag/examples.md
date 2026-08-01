<<<<<<< HEAD
# RAG Evidence

Verification: ingestion script processes a known document corpus and all chunks land in the index; a retrieval test with a known query returns the expected source document in the top-k; an end-to-end test with a golden Q&A pair produces an answer that cites the correct source; access-control test confirms a restricted document is not returned for an unauthorised user query.
=======
# RAG Examples

## Minimal production change
1. Update ingestion mapping with stable ids + metadata.
2. Rebuild affected index partition with explicit embedding version.
3. Add retrieval response fields: citations, scores, and filter summary.
4. Add evaluation case proving relevant chunk retrieval and faithful answer.

## Evidence to attach
- Index migration/backfill notes
- Retrieval/evaluation test output (recall@k or pass/fail fixture)
- Security check for ACL filtering and prompt-injection handling
>>>>>>> origin/main
