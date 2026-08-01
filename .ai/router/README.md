# Agent Router

Use `python .ai/engine/ai_kit.py route T<n>` to return the assigned v2 role
contract, scoped technology knowledge, imported core skills, and minimal task
context paths. Assignment follows the task owner set by Planner; Router does
not silently reassign work.

<<<<<<< HEAD
## Basic Usage

```bash
python .ai/engine/ai_kit.py route T1
```

Returns JSON with: `task`, `owner`, `tags`, `role_contract`, `skills`,
`context`, `triggered_by`, `extra_concerns`, `loading_order`.

## Explain Mode

```bash
python .ai/engine/ai_kit.py route T1 --explain
```

Adds an `explain` key with human-readable reasoning for every decision:
- `role_owner_mapping` – which domains the role owns and from which config source
- `stack_match` – active stack tags (kit.yaml + task tags) used for filtering
- `trigger_matches` – AI concern triggers that fired, matched via keyword or tag
- `skill_selection` – each selected skill with the reason it was included
- `excluded_domains` – domains that exist but are not in scope for this role

## Skill Loading Order

The router result always includes a `loading_order` list. Agents must follow it:
1. Load `role_contract` documents (role rules and checklist).
2. For each entry in `skills`: load `overview.md` first to understand scope.
3. Load phase-specific documents (`patterns.md`, `best-practices.md`) as needed.
4. Load `pitfalls.md` and `examples.md` when validating or writing evidence.
5. Load `context` files for workspace plan and task list.

## AI Trigger Routing

The router contains an executable trigger registry (`AI_TRIGGERS` in
`ai_kit.py`). Triggers activate when a keyword appears in the task title or a
tag matches. Activated triggers add AI-domain skills and flag cross-cutting
concerns (security, qa, performance, integration, architect).

### Trigger Schema

Each trigger entry in `AI_TRIGGERS` has:

| Field | Type | Description |
|---|---|---|
| `keywords` | list[str] | Case-insensitive substrings matched against task title |
| `tags` | list[str] | Tag values that activate the trigger |
| `extra_skills` | list[str] | Repo-relative paths to skill `overview.md` files to add |
| `extra_concerns` | list[str] | Role concern names to flag (informational) |
| `reason` | str | Human-readable explanation shown in `--explain` output |

### Trigger Precedence

1. Owner→domain skill scan runs first (from `registry.yaml` `owners`).
2. AI trigger augmentation runs after, adding only skills not already present.
3. Triggers never remove or replace domain-scoped skills.
4. Tasks with no matching trigger keywords or tags receive no trigger skills
   (unrelated tasks do not load all AI skills).

### Current Triggers

| Trigger | Keywords / Tags | Extra Skills | Extra Concerns |
|---|---|---|---|
| `llm` | "llm", "language model", "gpt", "inference", "completion" / tags: llm, ai, openai | openai/overview.md | security, performance |
| `rag` | "rag", "retrieval", "vector", "embedding", "chunk" / tags: rag, retrieval | rag/overview.md | security, qa |
| `prompt-injection` | "prompt injection", "indirect injection", "jailbreak" / tags: prompt-injection | — | security |
| `latency-cost` | "latency", "token budget", "rate limit", "cost optim" / tags: latency, cost | — | performance |
| `external-provider` | "openai api", "anthropic api", "provider contract" / tags: openai, provider | openai/overview.md | integration |
| `evaluation` | "eval", "benchmark", "recall@", "faithfulness" / tags: eval, evaluation | rag/overview.md | qa |
| `architecture` | "ai architecture", "llm pipeline", "multi-agent" / tags: architecture, pipeline | — | architect |

## Skill Metadata

Every technology skill directory under `.ai/skills/<domain>/<technology>/`
includes a `skill.meta.yaml` sidecar file. See `.ai/skills/SKILL-METADATA.md`
for the full contract. The router uses the `supported_stack` field to
supplement stack-based filtering.
=======
Route output includes:

- `skills` (backward-compatible list of selected entrypoints)
- `skill_details` (name/path/entrypoint/documents/selection reasons/loading
  phase/loading order/type)
- `trigger_matches` (registry trigger hits and rationale)
- `loading_instructions` (progressive loading contract)

Use `python .ai/engine/ai_kit.py route T<n> --explain` for token-level and
phase-level selection diagnostics. Trigger rules are configured in
`.ai-config/registry.yaml` under `skill_triggers`.
>>>>>>> origin/main
