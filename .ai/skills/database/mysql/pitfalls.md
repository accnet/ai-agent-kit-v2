# MySQL Pitfalls

- Directly adding NOT NULL columns with no default on populated tables.
- Assuming optimizer picks intended index without validation.
- Using implicit type coercion in predicates, causing index misses.
- Missing rollback notes for irreversible migrations.
