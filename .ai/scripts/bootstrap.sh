#!/usr/bin/env bash
# v2 adaptation of v1 bootstrap: initialize state and validate local contracts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

mkdir -p .ai-work/{logs,phases,plan,reports,roadmap,state,tasks}
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git config core.hooksPath .githooks
fi
if [[ ! -f .ai-work/state/workflow.json ]]; then
  python3 .ai/engine/ai_kit.py init --title "Untitled workflow" --workflow feature >/dev/null
fi
bash .ai/scripts/check-kit.sh
python3 .ai/engine/ai_kit.py validate
echo "AI-Kit v2 bootstrapped. Create tasks with .ai/engine/ai_kit.py add-task."
