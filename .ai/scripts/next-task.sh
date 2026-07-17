#!/usr/bin/env bash
# v2 adaptation of v1 next-task.sh: Scheduler returns only dependency-ready work.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec python .ai/engine/ai_kit.py ready
