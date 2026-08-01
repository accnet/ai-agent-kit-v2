# Vitest Testing Pitfalls

- Over-mocking the system under test until the test only proves the mocks return what
  they were told to return, not that the real code works.
- Depending on test execution order — state from one `it` block leaking into the next
  instead of each test setting up and tearing down its own state.
- Leaving a real network call unmocked (`fetch`, `axios`), making the suite flaky and slow
  instead of using `vi.mock` or an HTTP interceptor.
- Forgetting `vi.useRealTimers()` after `vi.useFakeTimers()` in one test, causing an
  unrelated later test in the same file to hang or time out.
- Asserting on implementation details (a specific internal function was called with
  specific args) so a valid refactor breaks tests that never should have cared.
