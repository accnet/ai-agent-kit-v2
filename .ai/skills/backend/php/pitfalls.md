<<<<<<< HEAD
# PHP Backend Pitfalls

Do not concatenate user input into SQL queries; always use prepared statements or the ORM query builder. Do not suppress errors with `@`; fix root causes. Do not store secrets in code or committed `.env` files. Avoid `eval()` and `exec()` with untrusted input. Do not bypass type declarations by suppressing or ignoring type errors. Do not use `die()`/`exit()` for error flow in library code; throw exceptions. Avoid global mutable state and static side effects that make unit testing impossible. Do not import packages that update `composer.lock` with unchecked version ranges — pin or range-lock all direct dependencies.
=======
# PHP Pitfalls

- Hidden dynamic typing assumptions that bypass validation.
- Fat controllers with cross-cutting logic.
- Swallowing exceptions and returning ambiguous null/false values.
- Updating package versions without checking lockfile and compatibility matrix.
>>>>>>> origin/main
