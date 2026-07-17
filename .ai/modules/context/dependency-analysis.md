<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: dependency-analysis
description: Find code affected by the change, so nothing breaks outside the task's visible scope.
---

# Dependency Analysis

## Purpose
Find code affected by the change, so nothing breaks outside the task's visible scope.

## When to Load
Any task that modifies existing code. Skip for greenfield additions.

## Process
1. From each file to be changed, trace: who imports it, who calls the changed symbols
2. Trace outward one level; go deeper only along public contracts (APIs, events, schemas)
3. Check non-code dependents: configs, migrations, docs, tests referencing the change
4. Classify each dependent: must-update / must-verify / unaffected

## Rules
- Public contract change → ALL consumers are must-verify, no sampling
- Shared utility change → check every caller, however tedious
- Dependent found in another feature's scope → report to Planner, don't quietly edit it

## Output
Impact list: file → classification → why. Must-update items become tasks in tasks.md.
