#!/usr/bin/env bash
# Validate v2 technology skill directories.
#
# Usage:
#   bash .ai/scripts/check-skills.sh          # validate all technology skills (default)
#   bash .ai/scripts/check-skills.sh all       # same as default
#   bash .ai/scripts/check-skills.sh ai        # validate only the ai domain
#
# Checks performed on each technology skill directory:
#   1. All five required documents are present and non-empty.
#   2. No placeholder markers in any required document.
#   3. skill.meta.yaml is present with all required fields.
#   4. skill.meta.yaml domain/technology fields match the directory path.
#
# Core skills (.ai/skills/core/*) are always validated for SKILL.md presence.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

mode="${1:-all}"
fail=0

# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
bad() { echo "FAIL: $1" >&2; fail=1; }

check_placeholder() {
  local file="$1"
  if grep -qiE 'PLACEHOLDER|not yet written|generic kit template' "$file" 2>/dev/null; then
    bad "placeholder content detected: $file"
  fi
}

check_meta() {
  local folder="$1"
  local meta="$folder/skill.meta.yaml"
  if [[ ! -f "$meta" ]]; then
    bad "missing skill.meta.yaml: $folder"
    return
  fi
  # Validate required fields
  local required_fields="skill_name domain technology owner version reviewed_at supported_stack"
  for field in $required_fields; do
    if ! grep -qE "^${field}:" "$meta"; then
      bad "skill.meta.yaml missing field '${field}': $meta"
    fi
  done
  # Validate reviewed_at format (YYYY-MM-DD)
  local reviewed
  reviewed=$(grep -E '^reviewed_at:' "$meta" | sed 's/reviewed_at:[[:space:]]*//' | tr -d '"' | tr -d "'")
  if [[ -n "$reviewed" ]] && ! echo "$reviewed" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
    bad "skill.meta.yaml reviewed_at must be YYYY-MM-DD, got '${reviewed}': $meta"
  fi
  # Validate domain matches directory
  local dir_domain
  dir_domain=$(echo "$folder" | sed 's|.*\.ai/skills/||' | cut -d/ -f1)
  local meta_domain
  meta_domain=$(grep -E '^domain:' "$meta" | sed 's/domain:[[:space:]]*//' | tr -d '"' | tr -d "'")
  if [[ -n "$meta_domain" && "$meta_domain" != "$dir_domain" ]]; then
    bad "skill.meta.yaml domain '${meta_domain}' does not match directory domain '${dir_domain}': $meta"
  fi
  # Validate technology matches directory
  local dir_tech
  dir_tech=$(echo "$folder" | sed 's|.*\.ai/skills/||' | cut -d/ -f2)
  local meta_tech
  meta_tech=$(grep -E '^technology:' "$meta" | sed 's/technology:[[:space:]]*//' | tr -d '"' | tr -d "'")
  if [[ -n "$meta_tech" && "$meta_tech" != "$dir_tech" ]]; then
    bad "skill.meta.yaml technology '${meta_tech}' does not match directory technology '${dir_tech}': $meta"
  fi
}

check_tech_folder() {
  local folder="$1"
  for document in overview patterns best-practices pitfalls examples; do
    local file="$folder/$document.md"
    if [[ ! -s "$file" ]]; then
      bad "missing or empty: $file"
    else
      check_placeholder "$file"
    fi
  done
  check_meta "$folder"
}

# ------------------------------------------------------------------
# select folders to check
# ------------------------------------------------------------------
if [[ "$mode" == "ai" ]]; then
  target_dirs=()
  while IFS= read -r d; do
    target_dirs+=("$d")
  done < <(find .ai/skills/ai -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)
else
  # all (default)
  target_dirs=()
  while IFS= read -r d; do
    [[ "$d" == .ai/skills/core/* ]] && continue
    target_dirs+=("$d")
  done < <(find .ai/skills -mindepth 2 -maxdepth 2 -type d 2>/dev/null | sort)
fi

for folder in "${target_dirs[@]}"; do
  check_tech_folder "$folder"
done

# ------------------------------------------------------------------
# core skills always validated (SKILL.md presence only)
# ------------------------------------------------------------------
for folder in .ai/skills/core/*; do
  [[ -d "$folder" ]] || continue
  [[ -s "$folder/SKILL.md" ]] || bad "$folder/SKILL.md missing or empty"
done

if [[ "$fail" -eq 0 ]]; then
  echo "v2 skills valid (mode: ${mode})"
fi
exit "$fail"
