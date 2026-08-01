# Vite Frontend Evidence

```ts
// src/env.ts
const required = (name: string): string => {
  const value = import.meta.env[name];
  if (!value) throw new Error(`Missing required env var: ${name}`);
  return value;
};

export const env = {
  apiBaseUrl: required('VITE_API_BASE_URL'),
  mode: import.meta.env.MODE,
};
```

Evidence: a successful `vite build` output, an env-validation test (a missing variable
throws at startup rather than surfacing as `undefined`), an alias-resolution test or
type-check pass, and a bundle-size comparison when the change adds or removes a
dependency.
