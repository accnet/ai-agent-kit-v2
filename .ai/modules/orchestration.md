# orchestration Module

## Purpose
Coordinate the orchestration concern across planning, implementation, verification, and review.

## Required Inputs
Task acceptance criteria, changed paths, relevant skill guidance, and current workflow state.

## Process
1. Load `.ai/skills/core/workflow-orchestration/SKILL.md`, plus domain-specific skills.
2. Convert findings into owned tasks and evidence artifacts.
3. Do not advance the lifecycle gate until the checklist evidence exists.

## Output
A task update, evidence path, and residual-risk statement.
