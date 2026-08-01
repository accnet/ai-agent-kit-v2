# React Vite Pitfalls

- Fetching data inside a deeply nested presentation component instead of a route/loader
  boundary, making the component impossible to test or reuse without network mocking.
- Swallowing a rejected promise from `fetch`/`axios` so the UI silently shows stale or
  empty state instead of surfacing an error.
- Using the array index as `key` in a list that can reorder or filter, so state (focus,
  input value) attaches to the wrong row after a reorder.
- Reading a secret or server-only value through `import.meta.env.VITE_*` — anything
  prefixed `VITE_` is inlined into the client bundle and visible to any user.
