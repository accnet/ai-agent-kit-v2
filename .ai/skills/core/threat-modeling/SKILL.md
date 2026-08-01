---
name: threat-modeling
description: Identify threats, abuse cases, mitigations, and residual risk for a feature before implementation.
version: 2.1.0
tier: core
stack: [any]
owner: security
gates: [G1, G3]
related: [security-review]
---

# Skill: threat-modeling

## Purpose
Surface exploitable threats at design time — before code is written and vulnerabilities are
cheaper to fix than after review. Where `security-review` audits a diff, threat-modeling
audits a *plan*, so security controls are baked into the architecture rather than patched in
at the end. Run at G1 for any task that touches auth, external integrations, AI inputs, or
sensitive data.

## When to use
A new feature, workflow, or integration that involves: untrusted input from users or external
systems, authentication or authorization logic, sensitive data (PII, credentials, financial
records), AI prompt inputs or tool outputs, privileged actions (admin operations, production
mutations), or a new trust boundary (new external API, new queue consumer, new public
endpoint).

## Procedure

1. **Enumerate assets and their sensitivity.** List what the feature creates, reads, updates,
   or deletes: data stores, secrets, user records, financial state, audit logs. Classify each
   as public, internal, or sensitive. Focus protection effort on sensitive assets — everything
   else gets baseline controls.
2. **Draw trust boundaries.** Identify every place where data or control crosses a trust
   level: public internet → load balancer, load balancer → service, service → database,
   service → third-party API, user browser → backend, AI prompt → tool execution. Each
   crossing is a threat surface. If a boundary isn't explicit in the design, add it.
3. **Enumerate threats using STRIDE.** For each trust boundary and sensitive asset, walk
   through:
   - *Spoofing*: can an attacker impersonate a user, service, or provider?
   - *Tampering*: can an attacker modify data in transit or at rest without detection?
   - *Repudiation*: can a user deny an action because no audit log captures it?
   - *Information Disclosure*: can an attacker read data they shouldn't (via logs, errors,
     over-fetching, timing side channels)?
   - *Denial of Service*: can an attacker exhaust resources (rate limit, queue flood,
     expensive query)?
   - *Elevation of Privilege*: can a low-privilege caller reach a high-privilege operation
     (IDOR, broken JWT validation, prompt injection to tool with elevated permissions)?
4. **Prioritize by impact × exploitability.** Rank threats: High (direct data loss, auth
   bypass, RCE), Medium (indirect leakage, DoS of non-critical path), Low (best-practice
   gap with no current exploit path). Focus mitigations on High and Medium; record Low as
   accepted residual risk with an owner.
5. **Design concrete mitigations.** For each High/Medium threat, specify the control:
   not "validate inputs" but "validate webhook HMAC-SHA256 signature using constant-time
   comparison before processing payload." Each mitigation must be implementable and testable.
   If no mitigation is feasible within scope, escalate before proceeding.
6. **Verify mitigations with targeted tests.** For each mitigation, write at least one
   adversarial test: a request with a forged signature should return 401, not process;
   a prompt injection attempt should not reach the tool execution path; an IDOR attempt
   should return 403, not the target resource. These tests are evidence for G3.
7. **Record residual risk.** List any threats that are accepted (not mitigated) with: the
   threat description, the reason it's accepted (out of scope, low exploitability, compensated
   by another control), and the owner responsible for monitoring it. Residual risk with no
   owner is not accepted risk — it's unmanaged risk.

## Checklist
- [ ] Asset inventory with sensitivity classification completed
- [ ] Trust boundaries identified for every external interaction
- [ ] STRIDE enumeration covers each boundary and sensitive asset
- [ ] Threats ranked by impact × exploitability; High/Medium have concrete mitigations
- [ ] Each mitigation is specific enough to implement and test
- [ ] Adversarial tests written for High/Medium mitigations
- [ ] Residual risks documented with owner and acceptance rationale

## Anti-patterns
- Assuming internal service callers are always trusted — lateral movement inside a network
  is a real attack path; internal services need authz checks too.
- Writing "validate all inputs" as a mitigation — this is a direction, not a control; specify
  the validator, the schema, and the rejection behavior.
- Relying on LLM prompt instructions as the sole defense against prompt injection — a policy
  is not enforcement; tool execution boundaries and allow-lists are.
- Leaving High-severity threats as "future work" TODOs — a known High threat that ships
  unmitigated is a vulnerability, not a task backlog item.
- Conflating threat modeling with `security-review`: modeling happens at G1 on the design;
  review happens at G3 on the diff. Both are required for security-sensitive features.

## Output
Threat model summary in `.ai-work/plan/` or the task plan, containing: asset list, trust
boundary diagram (text or diagram), STRIDE threat table with priority and mitigation, targeted
adversarial test evidence paths, and residual risk log with owners.
