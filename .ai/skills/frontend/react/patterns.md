# React Patterns

- **Derive, don't duplicate.** If a value can be computed from existing
  props/state during render, compute it — don't mirror it into a second
  `useState` that can drift out of sync.
- **Colocate state with where it's used**; lift it only as far as the
  nearest common ancestor that actually needs it. Reach for Context or a
  global store only once prop-drilling genuinely hurts, not preemptively.
- **`useEffect` is for synchronizing with an external system** (a
  subscription, a non-React widget, a DOM API) — not for computing derived
  state or responding to a prop change that a plain render-time
  calculation or event handler already covers.
- **Custom hooks for shared stateful logic** (`useDebouncedValue`,
  `usePagination`) instead of copy-pasting the same `useEffect`/`useState`
  pair across components.
- **Stable, meaningful `key` props** in lists — the item's own id, never
  the array index, whenever the list can reorder, filter, or have items
  inserted/removed.
- **Error boundaries** around a route/section, and `Suspense` for
  route-level or heavy-component code splitting (`React.lazy`), so one
  broken subtree or slow chunk doesn't blank the whole page.
- **Controlled inputs for anything validated or submitted**; uncontrolled
  (`ref`-based) only for simple, unvalidated, or performance-sensitive
  cases (e.g. a very large form where re-render on every keystroke is
  measured to matter).
- **Memoize only after measuring.** `useMemo`/`useCallback`/`React.memo`
  fix a proven re-render cost shown in the profiler — adding them
  everywhere by default adds complexity and dependency-array bugs without
  a proven benefit.
