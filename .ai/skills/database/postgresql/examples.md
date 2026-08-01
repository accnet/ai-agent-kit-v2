# PostgreSQL Examples

**Upsert instead of check-then-insert:**
```sql
INSERT INTO subscriptions (user_id, plan, updated_at)
VALUES ($1, $2, now())
ON CONFLICT (user_id)
DO UPDATE SET plan = EXCLUDED.plan, updated_at = EXCLUDED.updated_at;
```
Replaces a `SELECT` to check existence followed by a conditional
`INSERT`/`UPDATE`, which races when two requests for the same `user_id`
arrive concurrently.

**Adding an index without locking out writers:**
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer_id
  ON orders (customer_id);
```
Run outside a transaction block (most migration tools have a
"non-transactional migration" flag for exactly this). If the build fails
partway, Postgres leaves an `INVALID` index behind — drop and retry rather
than assuming it's usable.

**Batching a large backfill:**
```sql
DO $$
DECLARE
  affected integer;
BEGIN
  LOOP
    UPDATE orders
    SET normalized_status = lower(status)
    WHERE id IN (
      SELECT id FROM orders
      WHERE normalized_status IS NULL
      LIMIT 5000
    );
    GET DIAGNOSTICS affected = ROW_COUNT;
    EXIT WHEN affected = 0;
    COMMIT;
  END LOOP;
END $$;
```
Keeps each batch's lock window short instead of holding row locks across
the entire table for one giant `UPDATE`.

**Before implementing a new query or table**, find one existing model/query
in the project with a similar shape (same table, similar filter/join
pattern) and match its migration tool conventions, naming, and index
strategy; record any deliberate deviation and why in the task's review
evidence.
