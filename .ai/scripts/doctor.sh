#!/usr/bin/env bash
# Health check for the v2 nested agent and skill contracts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
fail=0
warn=0
ok() { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fail=1; }
note() { printf '  WARN %s\n' "$1"; warn=$((warn + 1)); }

echo "AI-Kit v2 doctor - $ROOT"
for file in AGENTS.md .ai-config/kit.yaml .ai-config/rules.yaml .ai-config/registry.yaml \
  .ai/engine/ai_kit.py .ai/scripts/check-kit.sh .ai/scripts/skills-for.sh .ai-work/state/current.json; do
  [[ -f "$file" ]] && ok "$file" || bad "$file missing"
done

PYTHON_CMD=${PYTHON_CMD:-$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)}
if [[ -n "$PYTHON_CMD" ]]; then
  ok "python found: $PYTHON_CMD"
else
  bad "python3 (or python) not found in PATH"
fi

if bash .ai/scripts/check-kit.sh; then
  ok "v2 contracts valid"
else
  bad "v2 contract validation failed"
fi

if [[ -f .ai-work/state/workflow.json ]]; then
  PYTHON_CMD=${PYTHON_CMD:-$(command -v python3 || command -v python)}
  "$PYTHON_CMD" .ai/engine/ai_kit.py validate >/dev/null && ok "workflow state valid" || bad "workflow state invalid"
else
  note "workflow state not initialized (run .ai/scripts/bootstrap.sh)"
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  hooks=$(git config --get core.hooksPath || true)
  [[ "$hooks" == ".githooks" ]] && ok "Git hooks configured" || note "Git hooks not configured; run bootstrap.sh"
fi

for key in test_command typecheck_command build_command lint_command; do
  cmd="$(awk -v key="$key" '$1 == key ":" {sub(/^[^:]*:[[:space:]]*/, ""); print; exit}' .ai-config/kit.yaml)"
  [[ -n "$cmd" ]] && ok "$key configured: $cmd" || note "$key not configured"
done

echo "summary: $fail failure(s), $warn warning(s)"
[[ "$fail" -eq 0 ]]
