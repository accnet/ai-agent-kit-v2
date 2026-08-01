# Scheduler Engine

The Scheduler is `python .ai/engine/ai_kit.py ready`. It derives runnable work
from canonical state: a task is runnable only when it is `todo` and every
dependency is `done`. Phase status is derived by the control plane and is not
edited manually.
