#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON_CMD=${PYTHON_CMD:-$(command -v python3 || command -v python)}
exec "$PYTHON_CMD" .ai/engine/ai_kit.py ready
