<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: workspace
description: Ephemeral .ai-work/ tier — session.md format, graduation rules, resume procedure. Load at session start/end.
---

# Module: Workspace

## Purpose
Define `.ai-work/` — the agent's ephemeral working state. Local only, never committed, safe to delete at any time.

## Four-Tier Model
| Tier | Content | Lifetime | Committed |
|---|---|---|---|
| `.ai/` | knowledge & process (roles, modules, commands, memory) | permanent | yes |
| `features/` | requirements & research (intent) | per feature | yes |
| `.ai-work/` | execution state (plan, tasks, architecture, progress) | per feature | yes |
| `.ai-work/` | session state, scratch, drafts | per session | **no** |

## Layout
```
.ai-work/
  session.md      current feature, current task, active agent role, next step
  scratch/        throwaway notes, POC snippets, command outputs
  drafts/         work-in-progress content not ready for .ai-work/ or code
```

## session.md Format
```
feature: <name>
task: <tasks.md line being executed>
role: <agent from .ai/agents/>
status: <one line — where things stand>
next: <first action when resuming>
```

## Rules
- Write `session.md` at start of work and update on every task switch — this is how a new session resumes without re-deriving context
- Parallel agents: each worktree carries its OWN `.ai-work/` (separate working dirs) — session.md is per-instance, never shared state; shared state lives only in committed `tasks.md`
- Anything worth keeping graduates OUT of `.ai-work/`: per-feature decisions → `.ai/memory/decisions.md`, tasks → `.ai-work/tasks/tasks.md`, requirements discovered → `.ai-work/requirements/` (via user/Researcher), code → the repo
- Never reference `.ai-work/` paths from committed code or docs
- `.ai-work/` is in `.gitignore`; agents must never `git add` it
- Deleting `.ai-work/` must lose nothing but convenience — if that's not true, something wasn't graduated

## Resume Procedure (new session)
1. `.ai-work/session.md` exists → resume from `next:`
2. Missing/stale → rebuild from `.ai-work/tasks.md` (source of truth) and `.ai-work/INDEX.md`, then rewrite session.md
