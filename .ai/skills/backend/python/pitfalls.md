# Python Backend Pitfalls

- Hidden global state causing test/order coupling.
- Broad `except Exception` blocks that hide root causes.
- Blocking I/O inside async paths without adapters.
- Dependency upgrades without lockfile/pin review.
