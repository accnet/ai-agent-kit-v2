# MySQL Examples

- Migration sequence: add nullable column -> batch backfill -> add index -> enforce NOT NULL.
- Validation evidence: migration dry-run output + explain plan before/after + targeted test.
