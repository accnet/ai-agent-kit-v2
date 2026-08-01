<<<<<<< HEAD
# Nginx Best Practices

Enable TLS 1.2+ only; disable SSLv3, TLSv1.0, TLSv1.1. Set HSTS with `Strict-Transport-Security` and a long `max-age`. Add `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and a `Content-Security-Policy` header appropriate for the application. Enable `gzip` compression for text content; set `gzip_min_length 1024`. Use `limit_req_zone` for rate limiting on authentication endpoints. Set `worker_processes auto` and tune `worker_connections` to match expected concurrency. Validate configuration before reloading (`nginx -t`). Set `server_tokens off` to suppress version disclosure.
=======
# NGINX Best Practices

- Validate configuration syntax before reload.
- Preserve real client IP headers only for trusted proxy chains.
- Add rate limiting and request size limits for exposed endpoints.
- Log with correlation ids and sanitized query/body fields.
>>>>>>> origin/main
