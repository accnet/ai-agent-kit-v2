#!/usr/bin/env bash
# v2 adaptation of v1 state.sh: canonical state is workflow.json, not Markdown.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec python .ai/engine/ai_kit.py show
