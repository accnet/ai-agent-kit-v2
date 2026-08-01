# React Best Practices

- Keep components small and focused on one responsibility; extract a
  child component or custom hook once a component mixes unrelated
  concerns (data fetching + layout + form logic).
- List every dependency `useEffect`/`useMemo`/`useCallback` actually reads
  in its dependency array — don't suppress the lint rule to silence a
  warning; fix the stale-closure or restructure the effect instead.
- Clean up subscriptions, timers, and event listeners in the effect's
  return function; an uncleaned interval/listener keeps firing against
  unmounted state.
- Use semantic HTML elements and label every form control (`<label
  htmlFor>` or `aria-label`) — accessibility comes from correct markup
  first, ARIA attributes second.
- Keep the render function pure: no mutation of props/state, no side
  effects, no non-deterministic values (`Date.now()`, `Math.random()`)
  computed directly in the render body without memoizing them.
- Code-split at the route level (`React.lazy` + `Suspense`) so the initial
  bundle only includes what the first screen needs.
- Handle loading, error, and empty states explicitly for anything async —
  a component that only renders the "happy path" is incomplete.
