# React Vite Best Practices

- Query the rendered DOM by role/label/text (Testing Library) instead of by CSS class or
  an ad hoc `data-testid` on every element.
- Validate keyboard navigation and focus order for interactive components (modals, menus)
  as part of the same task, not a follow-up.
- Keep `vite.config.ts` `resolve.alias` mirrored in `tsconfig.json` paths and in
  `vitest.config.ts`, so editor, type-check, and test resolution all agree.
- Treat `vite build` as part of verification whenever a change touches bundling, env
  vars, or dynamic imports — dev-server behavior can hide production-only failures.
