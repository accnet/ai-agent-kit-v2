# AI Safety Best Practices

- Define abuse cases per feature (prompt injection, data exfiltration, tool abuse).
- Test safety controls with adversarial fixtures.
- Default to deny for unsupported tool actions.
- Maintain allowlists for destinations/tools and strip secrets from context.
