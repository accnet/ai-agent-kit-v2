#!/usr/bin/env bash
# Print v2 knowledge documents relevant to a role and optional stack override.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
role="${1:-any}"
override="${2:-}"

domains="$(awk -v role="$role" '
  $1 == role ":" {gsub(/.*\[/, ""); gsub(/\].*/, ""); gsub(/,/, " "); print; found=1}
  END {if (!found) print "any"}
' .ai/registry.yaml)"
[[ -n "$override" ]] && domains="${override//,/ }"

for domain in $domains; do
  if [[ "$domain" == "any" ]]; then
    find .ai/skills -mindepth 2 -maxdepth 2 -type d ! -path '.ai/skills/core/*' | sort
  elif [[ -d ".ai/skills/$domain" ]]; then
    find ".ai/skills/$domain" -mindepth 1 -maxdepth 1 -type d | sort
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
  [[ -f "$path" ]] && printf '%s\n' "$path"
done
