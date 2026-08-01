# RAG Evidence

Verification: ingestion script processes a known document corpus and all chunks land in the index; a retrieval test with a known query returns the expected source document in the top-k; an end-to-end test with a golden Q&A pair produces an answer that cites the correct source; access-control test confirms a restricted document is not returned for an unauthorised user query.
