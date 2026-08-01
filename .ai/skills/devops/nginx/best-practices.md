# nginx Best Practices

> ⚠️ PLACEHOLDER — not yet written for nginx. This file still holds the generic kit template below, with no nginx-specific guidance. Do not treat it as real domain knowledge; replace it with actual nginx patterns/pitfalls/examples before relying on it.

- Follow pinned project versions and existing conventions.
- Validate untrusted input at boundaries.
- Keep secrets in environment-backed configuration, never source files.
- Add focused tests for changed behavior.
- Make operational impact observable where applicable.
