# LLM Application Patterns

- Define a clear request contract: user input, policy context, optional retrieved context, expected output schema.
- Implement orchestration as deterministic steps (prepare -> invoke -> validate -> post-process).
- Add failure classes (timeout, rate-limit, invalid-output, safety-block) with distinct handling.
- Keep provider adapters replaceable; orchestration layer should not depend on SDK internals.
