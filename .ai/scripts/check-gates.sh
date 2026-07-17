#!/usr/bin/env bash
# v2 adaptation of v1 G4 gate; safe in both Git and non-Git directories.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mode="${1:-all}"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ "$mode" == "staged" ]]; then files=$(git diff --cached --name-only --diff-filter=ACM); else files=$(git ls-files); fi
else
  files=$(find . -path './.ai-work' -prune -o -type f -print | sed 's#^./##')
fi
fail=0
while IFS= read -r file; do
  [[ -n "$file" ]] || continue
  [[ "$file" == .ai-work/* ]] && { echo "G4 FAIL: transient state must not be committed: $file" >&2; fail=1; }
  case "$file" in
    .env|.env.*|*/.env|*/.env.*) [[ "$file" == *.example || "$file" == *.sample ]] || { echo "G4 FAIL: environment file must not be committed: $file" >&2; fail=1; } ;;
    *.pem|*.p12|*.pfx|id_rsa|id_ed25519) echo "G4 FAIL: credential file must not be committed: $file" >&2; fail=1 ;;
  esac
  [[ -f "$file" ]] || continue
  case "$file" in *.png|*.jpg|*.jpeg|*.gif|*.pdf|*.zip) continue ;; esac
  if grep -nE '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{30,}' "$file" >/dev/null 2>&1; then
    echo "G4 FAIL: possible secret in $file" >&2; fail=1
  fi
done <<< "$files"
exit "$fail"
