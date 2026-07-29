# Workflow State Schema

`workflow.json` contains `version`, `title`, `workflow`, `tasks`, `phases`,
and `events`. A task has `id`, `title`, `owner`, `phase`, `needs`, `status`,
`acceptance`, `files`, `tags`, `attempts`, `evidence`, `blocked_reason`, and
`claimed_by`. Phase state is derived: `planned`, `open`, or `complete`.
`claimed_by` records the actor who started the task; QA and review actors
must differ from `claimed_by` to enforce independent verification.

Legal task statuses are `todo`, `in-progress`, `implementation-complete`,
`qa-passed`, `review-approved`, `done`, and `blocked`.

Legal actions are `start`, `complete`, `qa-pass`, `review-approve`, `close`,
`block`, and `unblock`. A task is runnable only when it is `todo` and every
dependency is `done`. IDs must be unique and the dependency graph must be a
DAG. Events are append-only and include timestamp, actor, action, task, old
status, new status, and detail.

`.ai-work/state/current.json` is a derived startup pointer maintained by State
Manager. It identifies the canonical workflow state and currently active tasks;
it is never an independent source of lifecycle truth.
