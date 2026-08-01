<<<<<<< HEAD
# PHP Backend Best Practices

Pin PHP to a specific minor version in `composer.json` (`php: "^8.2"`). Declare strict types at the top of every file. Use typed properties and return types; avoid `mixed` except at deserialisation boundaries. Leverage `readonly` classes for value objects. Handle exceptions at a single layer (global exception handler) and convert them to structured JSON error responses. Write unit tests with PHPUnit; mock I/O boundaries with interfaces. Enable OPcache in production and verify it in the health check. Run `composer audit` in CI to catch dependency vulnerabilities. Store sessions securely (HttpOnly, Secure, SameSite=Strict).
=======
# PHP Best Practices

- Confirm strict types usage and match existing coding standard config.
- Validate and sanitize input at boundary layers.
- Handle exceptions with domain-specific mapping and structured logs.
- Add/adjust tests at the same layer as the changed behavior.
>>>>>>> origin/main
