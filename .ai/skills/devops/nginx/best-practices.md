# NGINX Best Practices

- Validate configuration syntax before reload.
- Preserve real client IP headers only for trusted proxy chains.
- Add rate limiting and request size limits for exposed endpoints.
- Log with correlation ids and sanitized query/body fields.
