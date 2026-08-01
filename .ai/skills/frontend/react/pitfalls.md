# React Pitfalls

- **Infinite `useEffect` loops** from a dependency array that includes an
  object/array/function recreated every render — either memoize the
  dependency or narrow the array to the primitive values that actually
  need to trigger it.
- **Mutating state directly** (`state.items.push(x)` then calling
  `setState(state)`) — React compares references, so no re-render happens,
  or worse, other reads of the same object see the mutation early.
- **Array index as `key`** in a reorderable/filterable list — React
  reuses the DOM node by key, so index-based keys attach the wrong node's
  internal state (focus, input value, animation) to the wrong item after
  a reorder.
- **Stale closures in effects/callbacks** — an effect capturing a variable
  from an earlier render (because it was left out of the dependency
  array) acts on outdated data; this is usually a sign the effect should
  either include the dependency or read the latest value via a ref.
- **Calling hooks conditionally** (inside an `if`, loop, or after an early
  `return`) — breaks React's per-render hook-order assumption and causes
  hard-to-diagnose state mixups between unrelated hooks.
- **Prop drilling worked around with global state** for what's actually
  local UI state (a modal's open/closed flag) — adds cross-component
  coupling and re-renders for state only one subtree needs.
- **No code-splitting** on a large app — every route's code ships in the
  initial bundle, inflating time-to-interactive even for users who never
  visit most routes.
- **Overusing `useMemo`/`useCallback`** without measuring: the dependency
  array itself has a comparison cost, and a wrongly-scoped dependency
  array silently returns a stale memoized value instead of erroring.
