#!/usr/bin/env bash
# Run the local AI-Kit engine tests without writing state into the repository.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export PYTHONDONTWRITEBYTECODE=1
exec python3 -B -m unittest discover -s tests -v
