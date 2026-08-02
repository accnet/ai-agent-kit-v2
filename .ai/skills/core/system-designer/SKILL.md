---
name: system-designer
description: Translate a feature's domain into registered bounded contexts/modules with explicit ownership and acyclic dependencies (ai-kit context add), before requirement-decomposer creates tasks that reference them. Scoped to what actually feeds G6, Impact Analyzer, and the Knowledge Graph Builder — not a general DDD tutorial.
version: 0.1.0
tier: core
stack: [any]
owner: architect
gates: [G1, G6]
related: [.ai/engine/state-schema.md, architecture-decisions, requirement-decomposer]
---

# Skill: system-designer

## Purpose
Decide module/service boundaries and who owns them, and make that decision
durable and machine-checkable by registering it in `.ai-config/contexts.yaml`
— the same data `ai-kit context impact`, G6's `module_boundary` gate, and
`ai-kit analyze`'s Knowledge Graph Builder all read. A boundary that lives
only in a document nobody parses doesn't gate anything.

## When to use
Before task decomposition on any feature that introduces a new bounded
context/service, changes which role owns an existing one, or changes how
contexts depend on each other. Skip for a change entirely inside one
already-registered context — that's ordinary implementation work, not a
design decision.

## Procedure
1. **Identify the bounded context(s)** the feature touches: name the real
   business capability it owns end-to-end (`ordering`, `billing`), not a
   technical layer (`api`, `db`, `utils`).
2. **Assign the owning role** from AGENTS.md's Role Boundaries /
   `registry.yaml`'s `owners:`, based on who is accountable for the
   capability going forward — not just whoever implements it first.
3. **Decide dependency direction explicitly.** A cycle here is not a
   modeling nuance to note "for later": `ai-kit context add` raises on a
   dependency cycle outright, so resolve the direction before registering,
   not by working around the rejection.
4. **Register it**: `ai-kit context add <name> --path <glob> --owner <role>
   [--depends-on <existing-context> ...]`. The `--path` glob is exactly what
   G6 checks a task's `files` against — scope it to this context's own
   source tree; too wide and it silently swallows a neighboring context's
   files.
5. **Changing an existing context's boundary or owner**: use `--force` (it
   bumps the context's `revision`), so every task already recorded against
   the old shape surfaces as `context_stale` via `ai-kit drift` instead of
   going unnoticed.
6. **Hand the registered context names to `requirement-decomposer`**; tasks
   get tagged `--context <name>` from there. Design the graph first, tag
   tasks against it second — never the reverse.
7. **Run `ai-kit analyze`** after registering and check its `risks` list for
   `unowned_context` / `dangling_dependency` on what changed before treating
   the design as settled.

## Checklist
- [ ] Each new/changed context maps to one real business capability, not a
      technical layer
- [ ] Owner assigned from the existing role list, not left blank
- [ ] Dependency direction stated and acyclic (the engine enforces this —
      verify the design resolves the cycle rather than just hitting the
      rejection)
- [ ] `--path` glob registered and scoped to this context's own tree
- [ ] An existing context's boundary/owner change used `--force`, so drift
      tracking sees the revision bump
- [ ] `ai-kit analyze` run afterward with no new `unowned_context` /
      `dangling_dependency` for what changed

## Anti-patterns
- Drawing bounded contexts around technical layers instead of business
  capabilities
- Leaving a context unregistered because "it's obvious from the code" — G6,
  drift, and `ai-kit analyze` all read the registry, never the source tree
- Changing an owner or path without `--force`, silently breaking drift
  detection for tasks already recorded against the old context
- Designing a dependency cycle and treating the engine's rejection as an
  obstacle to route around instead of a signal to redesign the boundary
- Treating this skill as a DDD pattern catalog (aggregates, ubiquitous
  language, value objects, and the rest). That guidance, if the project
  wants it, belongs in a project-specific `architecture-decisions` record or
  its own documentation — this skill's job stops at registering the module
  and ownership graph the engine actually consumes.

## Output
`.ai-config/contexts.yaml` entries (module graph + ownership graph),
consumed by G6, `ai-kit context impact`, and `ai-kit analyze`.
