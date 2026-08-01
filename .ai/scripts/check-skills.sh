#!/usr/bin/env bash
# v2 adaptation of v1 check-skills.sh for nested technology and core skills.
# Fails on missing/empty files AND on placeholder marker content in ai/* skills.
#
# Environment variable override for testing:
#   CHECK_SKILLS_ROOT=/some/path  use this as the repo root instead of auto-detect
set -euo pipefail
ROOT="${CHECK_SKILLS_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT"
fail=0
for folder in .ai/skills/*/*; do
  [[ -d "$folder" ]] || continue
  for document in overview patterns best-practices pitfalls examples; do
    if [[ ! -s "$folder/$document.md" ]]; then
      echo "FAIL: $folder/$document.md missing or empty" >&2
      fail=1
    # Placeholder detection applies to the ai domain where production-ready
    # content is required. Other domains may be pending authoring.
    elif [[ "$folder" == .ai/skills/ai/* ]] && \
         grep -Eqi 'PLACEHOLDER|not yet written|generic kit template' "$folder/$document.md"; then
      echo "FAIL: placeholder content in $folder/$document.md" >&2
      fail=1
    fi
  done
done
for folder in .ai/skills/core/*; do
  [[ -d "$folder" ]] || continue
  [[ -s "$folder/SKILL.md" ]] || { echo "FAIL: $folder/SKILL.md" >&2; fail=1; }
done
[[ "$fail" -eq 0 ]] && echo "v2 skills valid"
exit "$fail"
