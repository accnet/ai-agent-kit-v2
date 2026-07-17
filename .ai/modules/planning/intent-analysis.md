<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: intent-analysis
description: Classify + size the request before planning (Sizing Gate; DB changes are never trivial).
---

# Intent Analysis

## Purpose
Classify the request before planning, so the right workflow and agents load.

## Classification
| Intent | Signals | Primary agents |
|---|---|---|
| feature | "add", "build", new capability | Planner → Architect → engineers |
| bug | "fix", "broken", unexpected behavior | Backend/Frontend → QA |
| refactor | "clean up", "restructure", no behavior change | Architect → engineer → Reviewer |
| research | "compare", "evaluate", "which library" | Researcher |
| release | "ship", "deploy", "version" | Release |

## Process
1. Restate the request in one sentence
2. Classify intent (one primary; note secondary if mixed)
3. Size the work (see Sizing Gate below)
4. Identify what is explicitly OUT of scope
5. List assumptions that need user confirmation

## Sizing Gate (scale-adaptive process)
| Size | Criteria (ALL must hold) | Process |
|---|---|---|
| **trivial** | ≤2 files, no database change (schema OR data), no contract/dependency change, behavior fully described in one sentence, reversible with one revert | Fast path |
| **standard** | one feature scope, known stack, no irreversible ops | Full pipeline |
| **large** | multiple domains, schema + API changes, migration, or irreversible steps | Full pipeline + Architect design doc + user plan approval before code |

**Fast path (trivial only)**: skip brief and full tasks.md. Single checklist inline:
```
- [ ] <the fix> — accept: <one verifiable criterion>
- [ ] test covering the fix passes (G2)
- [ ] self-review pass (G3-lite: security + convention check on the diff)
```
Gates G4/G5 still apply. If during a fast path ANY criterion of "trivial" breaks (third file, schema touched, a DB row changed...) → stop, upgrade to standard, write tasks.md.

## Rules
- **Any database change (schema OR data — migration, DDL, bulk/data update, seed) is never trivial**: it requires a full `tasks.md` (or a `.ai-work/`), never the fast path (rules.yaml: `db_changes_require_plan`, Gate G1)
- Mixed intent ("fix and also add...") → split into separate features
- Can't classify → ask the user, don't guess
- Refactor that changes behavior is a feature — reclassify
- When size is arguable, round UP — the cost asymmetry favors process

## Output
Intent label + size + one-sentence restatement + out-of-scope list, at the top of tasks.md (or inline checklist for trivial).
