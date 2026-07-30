# Workflow State Schema

`workflow.json` contains `version`, `title`, `workflow`, `tasks`, `phases`,
and `events`. A task has `id`, `title`, `owner`, `phase`, `needs`, `status`,
`acceptance`, `files`, `tags`, `attempts`, `evidence`, `blocked_reason`,
`claimed_by`, `context`, and `epic`. Phase state is derived: `planned`,
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
`tasks.md`, and persists through `unblock` (it is only cleared on `start`) so
the last reason a task was blocked stays visible in the human-readable view.
A task is runnable only when it is `todo` and every dependency is `done`.
IDs must be unique and the dependency graph must be a DAG. Events are
append-only and include timestamp, actor, action, task, old status, new
status, and detail.

`update-task` amends an existing task's `acceptance`, `files`, or `tags`
lists after creation (at least one of `--add-acceptance`, `--add-files`,
`--add-tags` is required) — use it when QA/review rejects work and the
acceptance criteria need to be tightened before redispatch, rather than
editing `workflow.json` by hand.

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
