# NestJS Data Access Pitfalls

- Returning ORM entities directly as API DTOs, leaking internal column names, relations,
  or lazy-loaded proxies to the client.
- Opening a transaction inside a controller instead of a service, so the transaction
  boundary doesn't match the actual unit of business work.
- Relying on `synchronize: true` (auto schema sync) in any environment beyond a
  developer's local machine — a production auto-sync can silently drop or alter columns.
- An N+1 query from lazy-loaded relations accessed in a loop, invisible until the table
  has enough rows for it to show up in latency.
