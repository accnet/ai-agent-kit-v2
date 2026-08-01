# MySQL Patterns

- Additive migrations first: add nullable column/backfill/enforce constraints later.
- Use explicit transaction scopes for consistent multi-step updates.
- Validate query plans (`EXPLAIN`) when adding or changing predicates.
- Prefer covering indexes for high-frequency read paths.
