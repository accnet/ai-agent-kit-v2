# MySQL Patterns

Express schema changes through versioned migration files (Flyway, Liquibase, Laravel migrations, or Knex); never apply ad-hoc DDL directly to production. Use InnoDB as the storage engine and UTF8MB4 character set for all tables. Prefer surrogate integer or UUID primary keys; add explicit indexes for every foreign key and every column that appears in a WHERE clause for large tables. Paginate with keyset (seek) pagination rather than OFFSET for large result sets. Wrap related mutations in a single transaction; keep transactions short.
