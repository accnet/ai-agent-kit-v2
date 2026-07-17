<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: context-assembler
description: Merge the trimmed context candidates into one coherent working set, in the order the task needs them.
---

# Context Assembler

## Purpose
Merge the trimmed candidates into one coherent working context, in the order the task needs them.

## Assembly Order
1. Task statement + acceptance criteria (verbatim)
2. Contracts: interfaces, schemas, API shapes the task must honor
3. Target file contents
4. Adjacent code (as trimmed by token-budget)
5. Conventions and rules (knowledge/ extracts)

## Rules
- Resolve conflicts explicitly: if two sources disagree (doc vs. code), code wins — and the mismatch is reported to Documenter
- Label each block with its source path, so claims are traceable
- No orphan snippets: anything assembled must be attributable to a candidate from the loader
- The assembled context is read-only during execution; new needs → re-run the pipeline

## Output
The working context the executing agent operates on. Pipeline ends here.
