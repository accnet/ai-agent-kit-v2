# Nginx Pitfalls

Do not expose directory listings (`autoindex on`) in production. Do not use weak cipher suites; test with `ssllabs.com` or `testssl.sh`. Do not allow unrestricted file upload without validating `Content-Type` and size limits. Do not use `alias` with a `location` block that ends with a trailing slash — it creates a path traversal vulnerability; use `root` instead. Do not log sensitive query parameters (API keys, tokens) in the access log without masking. Do not reload Nginx with invalid configuration — it will fail to start after a reboot.
