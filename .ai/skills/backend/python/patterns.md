# Python Backend Patterns

- Separate transport layer, domain logic, and persistence adapters.
- Keep side effects explicit and injectable for testability.
- Use typed dataclasses/pydantic-style DTOs where already adopted.
- Wrap external calls with timeout/retry/error mapping policy.
