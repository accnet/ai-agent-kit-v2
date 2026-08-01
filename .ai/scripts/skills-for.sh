#!/usr/bin/env bash
# Print v2 knowledge documents relevant to a role and optional stack override.
# Stack is resolved in priority order:
#   1. Explicit second argument (override)
#   2. project.stack from .ai-config/kit.yaml
#   3. Empty (no stack-specific filtering; uses registry owners)
#
# Environment variable override for testing:
#   SKILLS_FOR_ROOT=/some/path  use this as the repo root instead of auto-detect
set -euo pipefail

ROOT="${SKILLS_FOR_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT"
role="${1:-any}"
override="${2:-}"

# Read project.stack from kit.yaml when no explicit override is given.
# Uses only awk to stay dependency-free.
kit_stack=""
if [[ -z "$override" && -f ".ai-config/kit.yaml" ]]; then
  # Extract the value of "stack:" under the "project:" block.
  # Handles: stack: [openai, rag]  or  stack: []  or missing key.
  kit_stack="$(awk '
    /^project:/ { in_project=1; next }
    in_project && /^[^ ]/ { in_project=0 }
    in_project && /stack:/ {
      gsub(/.*stack:[[:space:]]*/, "")
      gsub(/[\[\]]/, "")
      gsub(/,/, " ")
      gsub(/[[:space:]]+/, " ")
      sub(/^[[:space:]]+/, "")
      sub(/[[:space:]]+$/, "")
      print
      exit
    }
  ' .ai-config/kit.yaml 2>/dev/null || true)"
fi

# Determine the effective stack (space-separated list or empty).
stack=""
if [[ -n "$override" ]]; then
  stack="${override//,/ }"
elif [[ -n "$kit_stack" ]]; then
  stack="${kit_stack//,/ }"
fi

# Resolve domains from registry owners when no stack override is active.
if [[ -z "$stack" ]]; then
  domains="$(awk -v role="$role" '
    $1 == role ":" {gsub(/.*\[/, ""); gsub(/\].*/, ""); gsub(/,/, " "); print; found=1}
    END {if (!found) print "any"}
  ' .ai-config/registry.yaml)"
else
  # Each stack value may be a domain name (e.g. "ai", "backend") or a
  # technology name (e.g. "openai", "rag"). Resolve both.
  domains="$stack"
fi

# Emit skill folder paths, de-duplicated.
for domain_or_tech in $domains; do
  if [[ "$domain_or_tech" == "any" ]]; then
    find .ai/skills -mindepth 2 -maxdepth 2 -type d ! -path '.ai/skills/core/*' | sort
  elif [[ -d ".ai/skills/$domain_or_tech" ]]; then
    # It's a domain name — list all technology skill folders under it.
    find ".ai/skills/$domain_or_tech" -mindepth 1 -maxdepth 1 -type d | sort
  else
    # Treat as a technology name — find the matching folder under any domain.
    find .ai/skills -mindepth 2 -maxdepth 2 -type d \
      -name "$domain_or_tech" ! -path '.ai/skills/core/*' | sort
  fi
done | awk '!seen[$0]++' | while IFS= read -r folder; do
  printf '%s\n' "$folder/overview.md"
done

case "$role" in
  planner|researcher) core="requirements-intake skill-router" ;;
  architect) core="refactoring api-contract" ;;
  backend) core="api-contract observability" ;;
  frontend) core="frontend-core test-and-validation" ;;
  database) core="data-migration api-contract" ;;
  devops|release) core="deployment-infra observability" ;;
  qa) core="test-and-validation debugging" ;;
  reviewer) core="code-review api-contract" ;;
  security) core="security-review threat-modeling" ;;
  integration) core="integration-contracts webhooks-and-retries" ;;
  performance) core="performance-profiling observability" ;;
  scheduler) core="workflow-orchestration" ;;
  router) core="workflow-orchestration skill-router" ;;
  document) core="documentation-maintenance architecture-decisions" ;;
  release) core="release-management deployment-infra github-actions-ci" ;;
  *) core="skill-router" ;;
esac
for skill in $core; do
  path=".ai/skills/core/$skill/SKILL.md"
  if [[ -f "$path" ]]; then printf '%s\n' "$path"; fi
done
