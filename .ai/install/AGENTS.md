# AI-Kit v2

This is the canonical entry point for every coding agent working in this
repository. Read it before planning, editing, reviewing, or releasing work.

## Source Of Truth

AI-Kit v2 is the source of truth for its architecture, paths, and contracts.
The earlier kit has been retired; its reusable guidance was adapted into v2 and
the migration record is kept in `.ai/memory/migration-v1.md`.

Keep these v2 contracts stable:

- `.ai/agents/<role>/` is a six-document role contract: `role.md`, `input.md`,
  `rules.md`, `prompt.md`, `checklist.md`, and `output.md`.
- `.ai/skills/<domain>/<technology>/` is curated technology knowledge with
  `overview.md`, `patterns.md`, `best-practices.md`, `pitfalls.md`, and
  `examples.md`.
- `.ai/workflows/<intent>/workflow.md` defines the delivery path.
- `.ai-work/` holds disposable work state, plans, tasks, reports, and logs.

Never rename, flatten, or replace these contracts as part of importing an idea
from v1. Adapt the idea to the v2 contract instead.

## Tool Compatibility

`AGENTS.md` is the only normative instruction source. Tool-specific files are
thin entry points and must not duplicate or override these rules:

- GitHub: `.github/workflows/gates.yml` runs portable validation in CI.
- GitHub Copilot: `.github/copilot-instructions.md` directs Copilot here.
- Cursor: `.cursor/rules/ai-kit.mdc` applies this file to every workspace task.
- Gemini CLI: `GEMINI.md` directs Gemini here.
- Antigravity: `ANTIGRAVITY.md` directs Antigravity here.
- Claude Code: `CLAUDE.md` and `.claude/commands/` direct Claude here.
- Windsurf: `.windsurf/rules/ai-kit.md` and `.windsurf/workflows/` direct
  Windsurf here.

All tools use the same control plane, local skills, state schema, and gates.
Do not introduce host-only skill paths, tool-specific state, or conflicting
task formats. Git hooks are defense in depth; CI and this file remain canonical.

## Scope And Quality

Build the kit by useful capabilities, not by target file count. A document,
template, agent, or skill is complete only when it provides actionable rules,
clear inputs and outputs, and a way to verify its use. Do not create skeletons,
empty placeholders, duplicate prompts, or generic content that cannot guide a
real task.

AI-Kit v2 is evolving into an executable multi-agent workflow engine for
controlled delivery of large projects in Codex and VS Code. It is not complete
until the orchestration components below have executable interfaces, durable
state transitions, and automated tests. Do not describe a prompt convention as
an engine capability without this evidence.

That last rule is enforced, not merely stated: `tests/test_agents_conformance.py`
parses the routing tables in this file and fails if any row is not actually
reachable through `.ai-config/registry.yaml`. Adding a row here without a
trigger behind it breaks the build. Extend the tests when adding a normative
table, so the claim and the implementation cannot drift apart.

Skill documents are tiered by depth on purpose (see README's "Skill depth is
tiered on purpose"). Most technology skills are short guardrails that stop
known mistakes, not tutorials; a few carry full worked references. Judge a
skill by whether every line is specific and actionable, never by its length or
by how many files a directory contains.

Prefer the smallest change that makes one capability reliably usable. Add a
new agent, skill, workflow, or automation only when it has a concrete owner,
trigger, interface, and verification path.

## Workflow Engine Architecture

The engine coordinates work through these components. Their contracts are
separate but share one canonical task and phase state model.

- **Planner:** turns a request into a roadmap, executable plan, tasks, phases,
  dependencies, risks, and acceptance criteria.
- **Scheduler:** validates the task dependency graph as a DAG, identifies
  runnable tasks, and opens a phase only when its dependencies are complete.
- **Agent Router:** chooses an eligible role, loads its role contract, scoped
  skills, and minimal context, and records why that assignment was made.
- **Executor:** performs an assigned phase, captures commands, changes,
  evidence, and handoff data without claiming review or QA authority.
- **Reviewer:** independently evaluates scope, contracts, coding standards,
  security, regressions, and residual risk.
- **QA:** verifies acceptance criteria through reproducible tests and reports
  failures back to the task state.
- **State Manager:** owns legal task and phase lifecycle transitions, claims,
  attempts, blocking reasons, and append-only execution history.
- **Context Engine:** ranks and loads the smallest relevant source, workflow,
  skill, decision, and test context for a specific assignment.
- **Memory Engine:** records durable architecture decisions, conventions, and
  postmortems separately from disposable session state.

The Scheduler, State Manager, and Agent Router are the control plane. They
must be deterministic for the same declared state and must reject invalid DAGs,
illegal transitions, missing acceptance criteria, and ambiguous task ownership.
The Planner, Executor, Reviewer, and QA are workers operating through that
control plane; no worker may bypass a gate by directly changing lifecycle state.

### Platform Capability Map

The components above are architectural roles, not new code to write. Each one
already exists as a concrete `ai-kit` command or artifact. This table is the
one normative place that maps the architect-role vocabulary onto what is
actually implemented, so the platform story stays honest instead of aspirational.
`tests/test_agents_conformance.py::PlatformCapabilityMapTests` asserts every
`ai-kit <command>` cell names a real subcommand and every artifact path is one
the engine actually writes.

| Role | Capability | `ai-kit` command / artifact |
| --- | --- | --- |
| Project Analyzer | Detects stack, tooling, and container/database runtime from the repo | `ai-kit onboard [--apply]` |
| Project Analyzer / Knowledge Graph Builder | Combines onboard's detection with contexts.yaml's module + ownership graph and static-analysis risk signals (unowned context, dangling dependency, no verification command) | `ai-kit analyze` -> `.ai-work/analysis/project-summary.json` |
| Impact Analyzer | Direct/transitive dependents and affected tasks for a module | `ai-kit context impact <name>` |
| Task DAG Builder | Task graph with waves, ready set, and critical path | `ai-kit visualizer generate` -> `.visualizer/dag.json`, rendered at `.visualizer/dag.html` |
| Execution Contract Builder | Self-contained JSON handoff for a dispatched task (owner, acceptance, routing, instructions) | written by `ai-kit dispatch` / `dispatch-ready` / `pipeline` to `.ai-work/handoffs/<task-id>.json` |
| Runtime Observer | Append-only audit trail of every state transition | `.ai-work/logs/events.jsonl`, surfaced as `.visualizer/events.json` by `ai-kit visualizer generate` |
| Scheduler Advisor | What can run now vs. what is blocked and why | `ai-kit ready`, `ai-kit blocked`, `ai-kit dispatch-ready` |
| Architecture / Module Graph | Module ownership and dependency graph from declared contexts | `ai-kit context list` -> `.visualizer/architecture.json` |
| Architecture Discovery | Read-only scan of the source tree for feature modules (NestJS/React/Python/generic) and internal import-based dependency edges, layered under declared contexts as parent/child, never mutating `contexts.yaml` | `ai-kit architecture discover` -> `.visualizer/discovered-architecture.json` |

This map only lists capabilities with a working command behind them today. A
role above this table without a row here (Planner, Reviewer, QA, Memory
Engine) is intentionally not included: it is fulfilled by an agent contract
and a gate, not by a queryable engine artifact, and adding a row for it here
without one would repeat the exact failure mode `test_agents_conformance.py`
already guards against.

`analyze`'s "Knowledge Graph Builder" half is deliberately scoped to the
Module Graph and Ownership Graph a project's own `.ai-config/contexts.yaml`
declares -- it is not a language-aware source parser, and does not extract
entities, API shapes, or call graphs from arbitrary code. A project that
never registers any contexts gets an empty graph, not a fallback scan of its
source tree; widening this into real code analysis is a new, separately
tested capability (`ai-kit architecture discover`, below), not a quiet
extension of `cmd_analyze`.

`architecture discover` is that separate, read-only capability. It scans the
configured source tree (`project.source_dirs` in `.ai-config/kit.yaml`, or
the repo root) for feature-level modules using framework conventions
(NestJS `*.module.ts`, React `src/{pages,components,features,services,
contexts}`, Python packages with `__init__.py`, and a generic first/second
-level fallback), attempts to detect internal dependency edges from
same-language relative imports, and writes the result to its own
`.visualizer/discovered-architecture.json` artifact. Contexts declared in
`.ai-config/contexts.yaml` remain the authoritative bounded contexts and are
never edited by discovery; a discovered module whose path falls inside a
declared context's glob is linked to it as a child (`parent` field) instead
of being treated as an unrelated top-level module. Anything discovery cannot
determine with confidence (unowned modules, dependencies pointing at a
module that does not exist, duplicate module paths, an unreachable source
root, a module with no owner or no related task) is recorded as a warning in
the artifact rather than guessed at or silently dropped. The command only
raises a hard error (non-zero exit) for a structurally invalid `contexts.yaml`
entry (for example a non-string `path`); everything else degrades to a
partial result with warnings. `.visualizer/app.js` fetches this artifact
independently of `architecture.json` and falls back to the declared-only
view when the file is absent, so existing consumers of `architecture.json`,
`ai-kit context list`, `context impact`, `visualizer generate`, `route`, and
`pipeline` are unaffected.

### Artifact Schema Versioning

Every artifact a worker or external tool consumes carries an explicit
version, so a consumer can detect a shape change instead of silently
misreading a renamed or retyped field:

- `.ai-work/state/workflow.json` has a top-level `version` (currently `2`);
  `.ai/engine/state-schema.md` documents its fields.
- `.ai-work/handoffs/<task-id>.json` (the Execution Contract Builder output)
  has `schema_version: 1`.
- `.visualizer/artifacts.json` is a manifest written alongside the other
  `.visualizer/*.json` payloads on every `ai-kit visualizer generate`: it
  has its own `schema_version` plus a per-file `artifacts: {filename:
  version}` map (`VISUALIZER_ARTIFACT_VERSIONS` in `ai_kit.py`). The
  payloads it describes (`board.json`, `architecture.json`, `impact.json`,
  `events.json`, `dag.json`) do not carry the version field themselves --
  they are keyed by task id, context name, or a fixed field set that
  `.visualizer/app.js` and `.visualizer/dag.html` read directly (pinned by
  `tests/test_visualizer_contract.py`), and mixing a `schema_version` key
  into one of those dicts would be misread as a task, module, or column.
- `.visualizer/discovered-architecture.json` is the one exception: it is a
  new, self-contained artifact (not keyed by task/module/context id), so it
  carries its own top-level `schema_version` field the same way the
  handoff JSON does, in addition to being listed in
  `VISUALIZER_ARTIFACT_VERSIONS`/`artifacts.json` like every other payload.

Bump the relevant version only when a payload's top-level shape changes in
a way a consumer must know about (a field added, removed, or retyped) --
not on every content change. `ai_kit._validate_visualizer_manifest` rejects
a malformed manifest (missing/mistyped `schema_version` or `artifacts`).

### Required Runtime Evidence

Before a component is marked implemented, provide:

- A documented input/output contract and error behavior.
- A persisted schema or explicitly versioned state format.
- Tests for normal, blocked, invalid, and recovery paths.
- An observable audit record explaining decisions and transitions.
- Compatibility with the stable v2 directory contracts above.

## Startup Procedure

1. Read `.ai-config/kit.yaml`, `.ai-config/rules.yaml`, and `.ai-config/registry.yaml`.
2. Read `.ai-work/state/current.json`. Resume only a current, scoped task.
3. Classify the request: feature, bugfix, refactor, migration, release, or
   research. Select its workflow and applicable role contract.
4. Load only the local technology knowledge needed for the task using
   `bash .ai/scripts/skills-for.sh <role>`.
5. Inspect relevant project files and tests. Existing project conventions take
   precedence over generic kit guidance.
6. Create or update `.ai-work/tasks/tasks.md` before implementation, unless
   the user explicitly waives G1 for this specific trivial documentation-only
   change.
7. For a new idea, use `python .ai/engine/ai_kit.py plan --idea ... --owner
   <role> --acceptance ...`; review its explicit assumptions before execution.
8. Execute within the declared scope, verify the acceptance criteria, record
   QA and review evidence paths, and obtain review before delivery.

## Skill And Concern Routing

Use `route T<n>` as the authoritative runtime assignment. It returns the role
contract, core skill entry points, stack-relevant technology knowledge,
structured skill metadata (entrypoint + document list + selection reasons +
loading phase/order), and minimal context. `route T<n> --explain` adds trigger
match evidence and token-level selection diagnostics. `skills-for.sh <role>` is
the equivalent discovery command before a task exists. Read the returned
`SKILL.md` or `overview.md`; do not load unrelated skill directories
speculatively.

These concerns are mandatory when their trigger is present:

| Trigger | Required role and core skills |
| --- | --- |
| Auth, untrusted input, sensitive data, permissions | Security: `security-review`, `threat-modeling` |
| External API, webhook, event consumer, retry | Integration: `integration-contracts`, `webhooks-and-retries` |
| Latency, memory, throughput, query volume | Performance: `performance-profiling`, `observability` |
| Parallel tasks, blocked work, handoff, retry | Scheduler/Router: `workflow-orchestration` |
| User journey or public API/event boundary | QA: `e2e-testing`, `contract-testing` |
| Cross-cutting choice or durable trade-off | Architect: `architecture-decisions` |
| Ship, CI, version, deployment, rollback | Release/DevOps: `release-management`, `github-actions-ci`, `deployment-infra` |
| UI interaction | Frontend: `accessibility`, `frontend-core` |
| New or upgraded dependency | DevOps: `dependency-management` |
| Schema or data change (migration, backfill, seed) | Database: `data-migration` |
| User, API, operational, or decision documentation | Document: `documentation-maintenance` |

AI trigger routing (registry-backed) is mandatory when matched by task content:

| Trigger | Required additions |
| --- | --- |
| Prompt injection / jailbreak / instruction override | Core `threat-modeling`, `security-review`; AI `ai-safety` |
| Latency / cost / token pressure | Core `performance-profiling`, `observability`; AI `llm-observability`, `ai-cost-management` |
| Evaluation / benchmark / quality regression | Core `test-and-validation`, `e2e-testing`; AI `model-evaluation` |
| External provider/API/webhook boundary | Core `integration-contracts`, `contract-testing`, `webhooks-and-retries`; AI `llm-application` |
| Architecture / pipeline orchestration | Core `architecture-decisions`; AI `agent-orchestration` |
| RAG / retrieval / embeddings | AI `rag`, `embeddings`, `vector-search`, `model-evaluation`; add `database/pgvector` or `database/qdrant` when stack/tags indicate it |
| LLM/model integration | AI `openai` or `llm-application` (as applicable), plus security/performance core concerns |

## Planning And Execution

Every non-trivial task record must state:

- Goal, scope, exclusions, risks, and open questions.
- Atomic tasks with owner, affected paths, dependencies, and observable
  acceptance criteria.
- Verification commands or other objective evidence.
- Review outcome and residual risk.

For a new idea, `plan` creates these initial artifacts:

- `.ai-work/roadmap/roadmap.md`
- `.ai-work/plan/plan.md`
- `.ai-work/tasks/tasks.md`
- `.ai-work/state/workflow.json` as the canonical lifecycle state

Work in dependency order. Parallel work must have disjoint file ownership or
an explicit integration owner. Re-plan when scope changes; do not silently
extend a task. Migration and database work always requires a plan, including
schema changes, data fixes, seeds, and backfills.

A feature that introduces or changes a bounded context/module boundary
follows this order: `requirements-intake` (WHAT is wanted) ->
`system-designer` (register the module/ownership graph in
`.ai-config/contexts.yaml` before any task references it) ->
`requirement-decomposer` (turn the brief into atomic, dependency-ordered
tasks, tagged against the contexts `system-designer` just registered). Both
are role-core skills (Planner, Architect) loaded unconditionally, not
keyword-triggered, since decomposition and boundary design are base
responsibilities of those roles on every task, not situational concerns.

## Multi-Stage Planning Pipeline

There is no single `ai-kit` command that runs a feature from raw request to
`done`. The recommended sequence chains the skills and commands documented
above; this section is that documentation, not a new command:

1. **Intake** (`requirements-intake`, judgment required): interpret the raw
   request into `.ai-work/requirements/brief.md` — problem, scope,
   acceptance criteria, open questions.
2. **Design** (`system-designer`, judgment required, only when a boundary
   changes): register the affected bounded context(s) via
   `ai-kit context add` before any task references them.
3. **Decompose** (`requirement-decomposer`, judgment required): turn the
   brief into atomic, dependency-ordered tasks via `ai-kit plan --idea ...`
   / `ai-kit add-task`.
4. **Route** (mechanical, deterministic): `ai-kit route T<n>` resolves the
   assigned role, core skills, and stack-relevant technology knowledge for
   each task the previous stage created.
5. **Execute one task** (mechanical once dispatched):
   `ai-kit pipeline T<n>` runs dispatch -> verify -> QA -> review -> close
   for that task, refusing to auto-approve when verification is
   inconclusive (G2) or when QA/review would run under the executor's own
   runner/model.
6. **Execute the runnable set** (mechanical): `ai-kit ready` /
   `ai-kit dispatch-ready --limit N`, repeated as completed tasks unblock
   their dependents.

Stages 1-3 are deliberately **not** chained into one command. Each one
requires interpreting free-form intent, weighing a trade-off, or naming a
domain concept — judgment this stdlib engine cannot perform and must not
fake. An engine-level command that "automated" this would either run a
heuristic that only pretends to write a brief/design, or silently re-host an
LLM call behind a function with no persisted schema, no failure mode, and no
test — exactly what "Required Runtime Evidence" above forbids. Stages 4-6
are already automated (`route`, `pipeline`, `dispatch-ready`) precisely
because their outcomes are deterministic and mechanically checkable.

`ai-kit pipeline` itself only ever advances **one already-created task**
through its execution lifecycle; it is not a multi-task or multi-stage
scheduler. It is synchronous (each phase blocks until the assigned runner
returns), has no background scheduler or auto-trigger, and there is no
automatic retry across phases (see its own docstring in `ai_kit.py`) -- a
stalled or failed phase simply stops and reports why. It is resume-capable:
if a previous run stopped partway (e.g. verify failed, or QA/review rejected),
re-running it skips straight to the first unfinished phase instead of
re-dispatching the executor. Running it across a feature's full task graph
means invoking it (or `dispatch-ready`) once per ready task, repeated as the
graph unblocks; that repetition is a documented operating procedure, not a
hidden capability to build.

## Gates

- **G1 - Plan:** before implementation, `.ai-work/tasks/tasks.md` has coherent,
  verifiable acceptance criteria. Database or migration work never uses a
  trivial fast path.
- **G2 - Task completion:** every acceptance criterion has evidence and the
  relevant configured checks pass before marking a task done. `qa-pass` and
  `review-approve` require at least one existing `--evidence` path.
- **G3 - Review:** a reviewer records `approve` with no unresolved blockers
  before delivery.
- **G4 - Hygiene:** never commit secrets, credentials, or transient
  `.ai-work/` state. Keep changes traceable to a task. `.ai-config/*.yaml`
  (`runners.yaml`'s runner commands; `kit.yaml`'s `test_command`,
  `lint_command`, `typecheck_command`, `build_command`) are executed as
  shell strings by the engine (`dispatch`, `verify`) — treat write access to
  these files as equivalent to arbitrary shell execution, and review changes
  to them with the same scrutiny as code, not as passive configuration.
- **G5 - Destructive operations:** require explicit user approval for the
  specific operation, including destructive data changes, force pushes, and
  production deployment.

### Configurable Gates

Gates G1 and G3 are configurable at runtime via `.ai-config/rules.yaml`. The engine
loads this file on every `validate()` call and applies the flags below:

| Rule key | Default | Affected gate | Behavior when `false` |
|---|---|---|---|
| `planning_first` | `true` | G1 | Allows tasks past `todo` in non-plan phases without completed plan dependencies |
| `review_required` | `true` | G3 | Allows tasks at `done` status without review evidence |

When a rule file is missing or malformed, the engine falls back to the safe
defaults shown above. See `.ai-config/rules.yaml` for the full list of supported
rules.

When a gate fails, leave the task open and record the failure. Do not hide
retries or mark partial work complete.

## Runner Autonomy

`ai-kit dispatch`, `dispatch-ready`, and `pipeline` hand a task off to a
configured runner CLI (`.ai-config/runners.yaml`) with stdin closed — the
runner cannot pause to ask a human for per-action permission, so its command
template necessarily includes a non-interactive/auto-approve flag
(`--permission-mode acceptEdits`, `--auto-approve true`, `--allow-all-tools`,
or the runner's equivalent). Without one, the runner's first tool-permission
prompt would hang or fail with no way to answer it.

This means the safety control for dispatched work is **not** per-action
confirmation during execution; it is the G2/G3 evidence and review gates
above, which run after the runner finishes. Do not dispatch a task to a
runner against a repository or task where unsupervised, full-tool-access
execution is unacceptable before that review happens. Runner model names in
`runners.yaml` are point-in-time examples tied to each provider's current
CLI — verify them against the installed CLI before relying on a pinned name,
since they will drift out of date.

## Role Boundaries

- Planner defines executable work and acceptance criteria; it does not invent
  requirements or implement unrelated code.
- Researcher gathers evidence and identifies unknowns; it does not silently
  convert assumptions into requirements.
- Implementers follow the assigned agent contract and existing project style.
- QA validates observable behavior and records reproducible failures.
- Reviewer looks for functional regressions, contract breaks, security issues,
  missing tests, and scope drift. Review is independent of implementation.
- Release checks verification evidence, compatibility, rollback information,
  and deployment approval.
- Security assesses threats and trust boundaries before allowing sensitive
  changes through review.
- Integration owns external contracts, webhook verification, retry safety, and
  failure behavior.
- Performance works from measured baselines and budgets, never intuition.
- Document keeps authoritative user, API, operational, and decision artifacts
  synchronized with delivered behavior.

## Context And Memory

Start from the owned task and nearby source. Load the smallest useful context:
the selected workflow, role contract, relevant skills, code, and tests. Keep
session-specific notes in `.ai-work/`. Promote durable conventions or decisions
only to the appropriate committed v2 documentation, never by treating
`.ai-work/` as permanent truth.

## Change Discipline

- Preserve user changes and avoid unrelated refactors.
- Use project-local references under `.ai/`; do not depend on host-specific
  agent skills to define repository behavior.
- Do not claim an action, test, or runtime capability exists without evidence.
- Record architecture decisions and durable lessons in `.ai/memory/`; keep
  task-specific evidence and reports in `.ai-work/`.
- Escalate unclear requirements, conflicting contracts, security-sensitive
  scope, or missing authority before taking irreversible action.

## Verification Commands

Run the local checks appropriate to the change:

```bash
python -m unittest discover -s tests -v
bash .ai/scripts/check-skills.sh
bash .ai/scripts/check-kit.sh
bash .ai/scripts/check-gates.sh all
```

Run `bash .ai/scripts/doctor.sh` after installing the kit or changing its
configuration. CI runs the same portable checks on GitHub.
