#!/usr/bin/env bash
# v2 adaptation of v1 check-skills.sh for nested technology and core skills.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
fail=0
for folder in .ai/skills/*/*; do
  [[ -d "$folder" ]] || continue
  for document in overview patterns best-practices pitfalls examples; do
    [[ -s "$folder/$document.md" ]] || { echo "FAIL: $folder/$document.md" >&2; fail=1; }
  done
done
for folder in .ai/skills/core/*; do
  [[ -d "$folder" ]] || continue
  [[ -s "$folder/SKILL.md" ]] || { echo "FAIL: $folder/SKILL.md" >&2; fail=1; }
done
[[ "$fail" -eq 0 ]] && echo "v2 skills valid"
exit "$fail"
