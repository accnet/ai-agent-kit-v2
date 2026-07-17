# Planner Engine

Planner creates the human-readable roadmap, plan, tasks, and phases, then
creates the same tasks in the control plane with `add-task`. It must provide
acceptance criteria and dependency IDs; the engine rejects unknown dependencies
and cycles. Planner never starts implementation tasks.
