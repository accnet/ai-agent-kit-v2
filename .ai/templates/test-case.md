<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

# Test Case — <unit under test>

Maps to: <tasks.md task ID + acceptance criterion>
Level: <unit | integration | e2e>
File: <project path, e.g. src/services/<thing>.service.test.ts>

## Setup / mocks
- <boundary mocked, e.g. mock the repository/dependencies at the seam>
- <fixtures / inputs>

## Cases
- [ ] <behavior> — given <state>, when <action>, then <expected>
  - asserts: <the boundary/return checked, e.g. the right arg passed down>
- [ ] <fallback/edge> — ...
- [ ] <error path> — given <no candidate available>, then <specific error thrown>

## Mutation check
Invert <key condition, e.g. a decision predicate>; expected: at least one case above fails.
Result: <fails as expected → revert | nothing failed → strengthen tests>

## Done
- [ ] All cases pass in the focused suite
- [ ] Full suite green (`kit.yaml verification.test_command`)
- [ ] Result recorded in the task note (e.g. "N suites, M tests passed")
