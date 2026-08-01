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
