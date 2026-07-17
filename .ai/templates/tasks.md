<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

# Tasks — <feature>

Intent: <feature|bug|refactor|research|release> | Size: <trivial|standard|large>
Goal: <one sentence>
Out of scope: <list>
Open questions: <blockers first, or "none">

## Tasks
- [ ] T1 <verb + object> | owner: <agent> | scope: S/M/L | needs: - | files: <paths this task owns>
  - Accept: <verifiable criterion>
- [ ] T2 <verb + object> | owner: <agent> | scope: S/M/L | needs: T1 | files: <paths>
  - Accept: <verifiable criterion>

## Tail
- [ ] T96 QA: integration test | owner: qa | needs: <all impl IDs> | files: tests/
- [ ] T97 Review (G3) | owner: reviewer | needs: T96 | files: -
- [ ] T98 Docs + graduation pass | owner: documenter | needs: T97 | files: -
- [ ] T99 INDEX.md state update | owner: release | needs: T98 | files: -

<!-- Machine-readable: .ai/scripts/next-task.sh parses this format.
     IDs are T<n>, unique per file. needs: comma-separated IDs or "-".
     Repo-native claim: append "| status: in-progress | instance: <name>" and commit. -->
