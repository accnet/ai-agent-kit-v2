# Vitest Testing Patterns

- Set the test environment per file glob (`environmentMatchGlobs: [["*.test.tsx", "jsdom"]]`)
  rather than one global `environment`, so node-only unit tests don't pay for a DOM they
  don't use.
- Use `vi.mock()` with an inline factory colocated in the test file, not a global
  `__mocks__` directory that silently applies to every test importing that module.
- Prefer `vi.spyOn(obj, 'method')` over mocking the whole module when only one function
  needs to be replaced — the rest of the module still exercises its real behavior.
- Use `test.each` / `describe.each` for table-driven cases instead of near-identical
  copy-pasted tests that only differ by one input/output pair.
- Configure `clearMocks: true` and `restoreMocks: true` in `vitest.config.ts` so tests
  don't need manual `afterEach(() => vi.clearAllMocks())` boilerplate in every file.
