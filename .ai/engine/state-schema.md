# Workflow State Schema

`workflow.json` contains `version`, `title`, `workflow`, `tasks`, `phases`,
and `events`. A task has `id`, `title`, `owner`, `phase`, `needs`, `status`,
`acceptance`, `files`, `tags`, `attempts`, `evidence`, `blocked_reason`,
`claimed_by`, `context`, `epic`, `base_commit`, `context_revision`,
`epic_revision`, `depends_on`, and `contract_hashes`.
Phase state is derived: `planned`,
`open`, or `complete`. `claimed_by` records the actor who started the task —
optionally suffixed `role#agent_id` (see Parallel agents below) — and QA and
review actors must differ from the *role* portion of `claimed_by` to enforce
independent verification. The
`verify` command is read-only: it runs configured checks, emits a report
dict (`task`, `checks`, `passed`), and never mutates task status, phase
state, or any lifecycle field — QA and review transitions remain the only
legal path from `implementation-complete`.

Legal task statuses are `todo`, `in-progress`, `implementation-complete`,
`qa-passed`, `review-approved`, `done`, and `blocked`.

Legal actions are `start`, `complete`, `qa-pass`, `review-approve`, `close`,
`block`, `unblock`, and `reject`. `reject` moves an `implementation-complete`
or `qa-passed` task back to `todo` and requires both a detail (reason) and an
actor different from `claimed_by` — use it instead of `block`/`unblock` when
QA or review finds work that must be redone, since `block` is for external
impediments (missing dependency, waiting on another team) rather than
rejected work. `blocked_reason` is set by `block`, surfaced in
`tasks.md`, and is cleared by `unblock` or `start`.
A task is runnable only when it is `todo` and every dependency is `done`.
IDs must be unique and the dependency graph must be a DAG. Events are
append-only and include timestamp, actor, action, task, old status, new
status, and detail.

`update-task` amends an existing task's `acceptance`, `files`, or `tags`
lists after creation (at least one of `--add-acceptance`, `--add-files`,
`--add-tags` is required) — use it when QA/review rejects work and the
acceptance criteria need to be tightened before redispatch, rather than
editing `workflow.json` by hand.

`--acceptance` (on `add-task`/`plan`) and `--add-acceptance` (on
`update-task`) both accept multiple values in one flag (`--acceptance "a"
"b"`) and can also be repeated (`--acceptance "a" --acceptance "b"`) — every
occurrence accumulates instead of the last one silently overwriting the
rest.

## Context / module boundaries

`context` is an optional free-form tag naming the bounded context or
service a task belongs to (e.g. `ordering`, `billing`, `ui`). Register
contexts in `.ai/contexts.yaml` (`ai-kit context add <name> --path <glob>
--owner <role>`, `ai-kit context list`) so `status`, `ready`, and `graph`
can be filtered with `--context`. When `module_boundary` is enabled in
`.ai/rules.yaml` (default `false`, opt-in), gate **G6** rejects a task whose
`files` list contains a path outside its registered context's glob — this
is what lets multiple agents work different services (api/ui/database) in
parallel without silently stepping on each other's files. A task with no
`context` is never checked by G6.

`epic` is an optional free-form tag grouping tasks that belong to the same
blueprint/feature across services (a blueprint split into api+ui+db tasks
shares one `epic` value). `ai-kit epics` reports per-epic totals and
`percent_done`; `status`/`ready` also accept `--epic` to filter.

An epic can optionally be registered in `.ai/epics.yaml` (`ai-kit epic add
<name> --spec <path> [--owner <role>]`, `ai-kit epic list`), pointing at its
**Specification** doc — the design/acceptance-criteria writeup the epic's
tasks were planned against. Registering it is what enables `epic_revision`
drift tracking below; an unregistered epic still works as a plain tag.

## Provenance and drift

Every task created by `add-task`/`plan` records three provenance fields,
automatically, with no CLI flag:

- `base_commit` — the repo's git HEAD at task-creation time (`null` outside
  git or before the first commit).
- `context_revision` — the registered `.ai/contexts.yaml` revision of the
  task's `context` at creation time (`null` if the task has no context, or
  the context wasn't registered yet).
- `epic_revision` — the registered `.ai/epics.yaml` revision of the task's
  `epic`'s Specification at creation time (`null` if the task has no epic,
  or the epic wasn't registered yet).

`ai-kit context add <name> --path <glob> --owner <role> --force` updates an
existing context and bumps its `revision`; `ai-kit epic add <name> --spec
<path> [--owner <role>] --force` does the same for an epic's Specification.
Either bump makes tasks recorded against the old path/spec detectable as
stale. `ai-kit drift <task-id>` reports, read-only: whether commits landed
since `base_commit` (with the list of changed files, via `git diff
--name-only`), whether the task's context has been revised since it was
created (`context_stale`), and whether the task's epic's Specification has
been revised since (`epic_stale`). `drift` never blocks a transition —
blueprints, specs, and contracts change legitimately during development;
it's a signal for a human/agent to decide whether a task needs a re-plan
before dispatch or review, not a gate.

Tasks can declare contract/interface files with repeatable
`--depends-on <path>` on `add-task` or `plan`. The engine reads each file
directly at creation time and stores `contract_hashes` as a dictionary from
the declared path to its SHA-256 content hash; no registry file is involved.
`ai-kit drift <task-id>` adds `contract_stale`, a list of declared paths whose
current hash differs from the recorded value, including paths that are now
missing. Unchanged paths are omitted. `drift` also reports
`drift_unavailable`, declared paths that raised an error on read (e.g. a
path replaced by a directory) rather than simply differing or being absent —
distinct from `contract_stale` so a read failure is never silently reported
as "healthy". `validate()` migrates older tasks by defaulting `depends_on` to
`[]` and `contract_hashes` to `{}`.

`ai-kit board [--context C] [--epic E] [--owner O] [--write]
[--format json|markdown]` is a read-only derived view grouped into all seven
`STATUSES` columns. Filters are exact and combinable. JSON always contains all
columns; Markdown omits empty sections. Entries include id, title, claimed
owner (or task owner), context, epic, optional `blocked_reason`, and read-time
flags: `blocked`, `context-stale`, `epic-stale`, `contract-stale`, and
`drift-unavailable`. The board and `drift` share one drift-flag computation;
flags are never written to `workflow.json`. `--write` additionally creates
`.ai-work/board.md` in Markdown without changing workflow revision. An
existing dependency path that cannot be read is unavailable, not stale;
missing paths retain the existing contract-stale behavior.

## Parallel agents

`save()` already serializes concurrent writers safely: a lock file guards
the read-check-write critical section and the write is rejected if the
on-disk `revision` no longer matches what the caller expected, so two
processes racing to claim the same task never corrupt state — the loser
gets a `state changed concurrently` error. `_retry_transition` (used by
`dispatch` and `dispatch-ready`) retries that loser a few times with
backoff, reloading fresh state and re-checking preconditions on every
attempt.

`--agent-id` on `transition`/`dispatch`/`dispatch-ready` records which
physical agent instance is executing, stored as `claimed_by: "role#agent_id"`
so multiple concurrent agents sharing one role (e.g. three `backend`
workers) remain distinguishable in the audit trail. `dispatch-ready
--runner X [--limit N] [--context C] [--epic E]` atomically claims up to N
ready tasks (auto-generating a unique `agent_id` per task if none is given)
and spawns each task's runner as a detached background process, so N
claimed tasks execute concurrently rather than one dispatch call blocking
the next.

`.ai-work/state/current.json` is a derived startup pointer maintained by State
Manager. It identifies the canonical workflow state and currently active tasks;
it is never an independent source of lifecycle truth.
