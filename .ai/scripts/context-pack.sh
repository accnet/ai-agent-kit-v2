#!/usr/bin/env bash
# v2 adaptation of v1 context-pack.sh: router emits deterministic minimal context paths.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
TASK="${1:?usage: context-pack.sh T<n>}"
exec python3 .ai/engine/ai_kit.py route "$TASK"
