# Tasks - v2 workflow engine

- [x] T1 Define canonical workflow state, lifecycle, and engine contracts | owner: planner | needs: -
  - Accept: state schema documents tasks, phases, dependencies, ownership, audit events, and legal transitions.
- [x] T2 Implement the Python control-plane CLI | owner: backend | needs: T1
  - Accept: CLI creates plans, validates DAGs, lists runnable work, transitions state, records events, and emits router context.
- [x] T3 Import and adapt v1 core skills into the v2 skill layout | owner: architect | needs: T1
  - Accept: every imported skill is discoverable by v2 routing and preserves its original source attribution.
- [x] T4 Adapt v1 automation into v2 wrappers and lifecycle scripts | owner: devops | needs: T2,T3
  - Accept: bootstrap, state, context, gate, and task-selection commands operate on `.ai-work` without a Git requirement.
- [x] T5 Add workflow-engine docs, role contracts, and a fixture workflow | owner: document | needs: T2,T3,T4
  - Accept: a new user can create, route, execute, QA, and review a sample workflow using documented commands.
- [x] T6 Run unit and end-to-end validation | owner: qa | needs: T5
  - Accept: tests cover valid/invalid DAGs, blocked/runnable scheduling, lifecycle rejection, routing, and audit logging.
- [x] T7 Review (G3) | owner: reviewer | needs: T6
  - Accept: no blocking contract, runtime, or compatibility issue remains.
