<<<<<<< HEAD
# Nginx Patterns

Organise configuration with an `nginx.conf` main file that includes `conf.d/*.conf` for sites and `snippets/` for reusable blocks (TLS settings, CORS headers, security headers). Use `proxy_pass` with an upstream block for backend services; set `proxy_set_header Host`, `X-Real-IP`, and `X-Forwarded-For`. Terminate TLS at Nginx; pass plain HTTP to backend services on the internal network. Define `location` blocks from most specific to least specific. Use `try_files` for single-page applications to route all paths to `index.html`.
=======
# NGINX Patterns

- Keep server blocks minimal and route-specific includes explicit.
- Use upstream blocks with health-aware failover and timeouts.
- Enforce HTTPS redirects and modern TLS settings through shared snippets.
- Set request/body/timeouts per endpoint sensitivity.
>>>>>>> origin/main
