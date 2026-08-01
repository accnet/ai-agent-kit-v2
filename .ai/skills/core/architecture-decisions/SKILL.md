---
name: architecture-decisions
description: Capture durable architecture decisions with alternatives, consequences, and review points.
version: 2.1.0
tier: core
stack: [any]
owner: architect
gates: [G1, G3]
related: [release-management, workflow-orchestration]
---

# Skill: architecture-decisions

## Purpose
Record cross-cutting design choices so future contributors understand not just *what* was
decided but *why*, what was rejected, and what would trigger a revisit. Undocumented
decisions create silent constraints — the next change breaks something for a reason no one
can articulate, because the original reasoning was never written down.

## When to use
Any decision that affects: module/service boundaries, data ownership, API shapes that other
teams consume, state lifecycle transitions, security trust boundaries, deployment topology,
or long-term maintenance cost. If a design choice would be surprising to a new contributor,
or if reversing it later would require migrating data or breaking consumers, document it.
*Implementation details* (which function to call, how to name a variable) do not need an
ADR.

## Procedure

1. **State the decision question and its constraints.** Write the question in a form that
   has a yes/no or multiple-choice answer: "Should we store workflow state in the database
   or in a flat JSON file?" Identify the constraints that limit options: latency budget,
   team familiarity, existing infrastructure, security requirements, licensing. Constraints
   that are unstated become assumptions that break later.
2. **List viable alternatives.** Include at least two options beyond the chosen approach.
   For each: what it enables, what it costs (complexity, latency, operational burden,
   migration effort), and why it was not chosen for *this context*. "We considered X but
   rejected it because it requires Y which we don't have" is more useful than "X was
   considered." Alternatives that were never seriously evaluated add noise — only list
   options that were genuinely considered.
3. **Describe the selected approach and its expected impacts.** Explain the chosen
   architecture: what components it introduces or changes, how data flows, what the
   ownership boundaries are, and how it integrates with existing systems. Include the
   concrete impact on: API contracts (new/changed shapes), data schemas (new tables/fields),
   deployment (new services/configs), and observability (what new signals are needed).
4. **Document migration and backward-compatibility.** If the decision changes an existing
   interface or data model, state explicitly: whether existing consumers break and need
   updating, what the migration path is (expand-migrate-contract or versioned cutover),
   and what the rollback looks like if the decision is reversed within the first release.
   A decision with no rollback path requires G5 approval before implementation.
5. **Record risks and open questions.** List what could go wrong, at what scale/load/edge
   case the approach might fail, and what would trigger a revisit (e.g., "revisit if queue
   depth exceeds 10k; flat-file state won't scale"). Assign an owner to each open question.
   An open question with no owner will never be answered.
6. **Link to tasks, acceptance criteria, and verification evidence.** An architecture
   decision is not complete until it references the task that implements it and the evidence
   that confirms the implementation matches the decision. If the task hasn't been created
   yet, create it. The decision record and the task record must stay in sync — if
   implementation diverges from the decision, update the record.

## Checklist
- [ ] Decision question is specific and answerable (not a vague goal)
- [ ] At least two genuine alternatives listed with rejection rationale
- [ ] Selected approach describes component changes, data flow, and ownership boundaries
- [ ] Concrete impacts on APIs, schemas, deployment, and observability are stated
- [ ] Migration/backward-compatibility and rollback path are documented
- [ ] Risks and open questions have owners and revisit triggers
- [ ] Linked to the implementing task and verification evidence

## Anti-patterns
- Writing an ADR *after* implementation to explain a decision that was made implicitly —
  by then, the rejected alternatives are forgotten and the constraints are post-hoc
  rationalizations, not the actual reasons.
- Using "we'll decide later" or "future work" as a substitute for documenting a known
  constraint — future contributors will make the wrong choice because the constraint
  was invisible.
- Recording implementation notes ("we used `uuid()` for IDs") as architecture decisions —
  ADRs document choices with significant trade-offs and lasting consequences, not every
  coding choice.
- Capturing the decision but not updating it when implementation diverges — a stale ADR
  is worse than no ADR, because it actively misleads.

## Output
Architecture decision record in `.ai-work/plan/architecture.md` or a dedicated
`.ai-work/plan/decisions/` file, containing: decision question, constraints, alternatives
with rejection rationale, selected approach with impact analysis, migration/rollback plan,
risks with owners, and links to the implementing task and its evidence.
