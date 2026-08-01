# React Overview

React renders UI from state via components and hooks; there is no
built-in store, router, or data-fetching layer — those are the project's
chosen libraries (Redux/Zustand/Context, React Router/Next router,
React Query/SWR/RTK Query). Check which ones are already in use before
adding a new one for a task-scoped change.

Check the React major version in use: 18+ has automatic batching,
`useId`, and concurrent-safe `useTransition`/`useDeferredValue`; 19 adds
the `use` hook, actions, and built-in form status hooks. Don't reach for a
version-gated API without confirming the installed version supports it.
