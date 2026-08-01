<<<<<<< HEAD
# Nginx Evidence

Verification: `nginx -t` exits 0, `curl -I https://<host>` returns 200 with HSTS and security headers, `curl http://<host>` redirects to HTTPS (301), a request exceeding the rate limit returns 429, and `testssl.sh <host>` shows no critical findings.
=======
# NGINX Examples

- New upstream route with dedicated timeout/rate-limit profile.
- Validation evidence: `nginx -t`, reload output, and smoke check of route + headers.
>>>>>>> origin/main
