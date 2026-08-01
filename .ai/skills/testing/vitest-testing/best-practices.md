# Vitest Testing Best Practices

- Mirror the app's `resolve.alias` in `vitest.config.ts`'s `test.alias` (or via
  `vite-tsconfig-paths`), or an import can resolve differently in a test than in the app.
- Call `vi.useFakeTimers()` explicitly where needed and restore with `vi.useRealTimers()`
  in `afterEach`; never leave fake timers active past the test that needed them.
- Run a scoped file or pattern (`vitest run path/to/file.test.ts`) locally before the full
  suite; reserve full-suite runs for CI.
- Assert on rendered output and behavior (Testing Library queries, return values) rather
  than on a component's internal state or a function's private calls.
- Set `coverage.thresholds` in config so a coverage regression fails the build instead of
  drifting down silently release after release.
