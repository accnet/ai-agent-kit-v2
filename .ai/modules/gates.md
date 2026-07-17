# Gates

G1 requires `.ai-work/tasks.md` with acceptance criteria before implementation.
G2 requires those criteria and relevant verification commands to pass before a
task is marked complete. G3 requires a recorded reviewer approval. G4 blocks
secrets and transient `.ai-work/` state from commits. G5 requires explicit user
approval for irreversible data changes, force pushes, and production deploys.

Failures stay visible in the task record; do not silently retry indefinitely.
