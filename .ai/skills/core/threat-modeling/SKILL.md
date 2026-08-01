---
name: threat-modeling
description: Identify threats, abuse cases, mitigations, and residual risk for a feature before implementation.
version: 2.0.0
tier: core
stack: [any]
owner: security
gates: [G1, G3]
related: []
---

# Skill: threat-modeling

## Purpose
Identify and mitigate exploitable threats across trust boundaries before shipping changes.

## When to use
Untrusted input, auth/permissions, sensitive data, external integrations, AI prompts/tools, or privileged actions are involved.

## Procedure
1. Map assets, entry points, trust boundaries, and attacker capabilities.
2. Enumerate abuse cases (spoofing, tampering, data exfiltration, privilege escalation, denial of service).
3. Prioritize threats by impact and exploitability; choose concrete mitigations.
4. Add validation, authorization, rate limiting, and audit controls where needed.
5. Verify mitigations with targeted security tests or adversarial fixtures.

## Checklist
- [ ] Threat list includes changed boundary surfaces.
- [ ] High-risk threats have implemented mitigations.
- [ ] Mitigations are testable and tested.
- [ ] Sensitive data handling and logging redaction are verified.
- [ ] Residual risks are recorded with owner and follow-up.

## Anti-patterns
- Assuming internal callers are always trusted.
- Relying on prompts/policies instead of enforcement for security controls.
- Leaving high-severity threats as undocumented TODOs.

## Output
Threat model summary + implemented controls + residual risk log.
