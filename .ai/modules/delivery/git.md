<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: git
description: Version-control conventions — branching, commits, worktrees, and parallel-agent coordination (claim-by-commit). Load before any commit, and when agents run in parallel.
---

# Module: Git

## Purpose
Version-control conventions for all agents that write files.

## Branching
- One feature = one branch: `feature/<feature-name>`; fixes: `fix/<short-desc>`
- Branch from the main integration branch; rebase or merge per the project's existing habit — don't introduce a new one

## Commits
- One commit = one task from tasks.md (or a coherent slice of it)
- Message: `<type>: <what changed and why>` — types: feat, fix, refactor, test, docs, chore
- Never commit: secrets, credentials, generated artifacts, commented-out code, unrelated formatting churn

## Rules
- Commit compiling, test-passing states — broken WIP stays local
- Schema migration and the code depending on it → same commit or migration first
- Force-push only on own feature branches, never on shared ones
- Before handoff to Reviewer: diff re-read by author agent (self-review pass)

## Worktrees & Parallel Agents

Applies when multiple agents work the same feature concurrently (see planner.md Orchestration). Single-agent work ignores this section.

### Setup (per claimed task)
```
git worktree add ../<repo>-wt/<feature>-<task-id> -b agent/<feature>-<task-id>
```
- One worktree per agent per task; never two agents in one working dir
- `agent/` branch prefix is mandatory — reviewers see machine-generated code before opening the diff; branch protection can target `agent/**`

### Coordination Modes
- **Mode A — tool-native**: if the host tool has coordination primitives (Claude Code Agent Teams shared task list, Codex multi-agent), use them. tasks.md stays the source of truth; the lead mirrors state both ways.
- **Mode B — repo-native** (any tool, independent sessions): claim-by-commit. To claim a task, commit its line in tasks.md with `status: in-progress, instance: <name>` and push. Push rejected = someone claimed first → rebase, pick another task. Git itself is the lock; no other infrastructure.

### Merge Discipline
- Merge order follows `needs:` in tasks.md — a branch never merges before its dependencies
- ≤3 parallel branches: rebase onto main before PR (linear history)
- >3 branches: integration branch — merge all agent branches there, run full tests, resolve conflicts, merge the clean result to main
- Conflict between two agent branches → the Orchestrator arbitrates; the task owning the contested file (per `files:`) wins, the other rebases
- Remove the worktree immediately after merge (`git worktree remove`); stale worktrees are the top failure mode

## Output
Clean, reviewable history where each commit maps to a task; parallel work isolated per worktree, integrated in dependency order.
