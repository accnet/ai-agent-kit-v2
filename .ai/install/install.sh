#!/usr/bin/env bash
# Install this nested AI-Kit into its parent project directory.
set -euo pipefail

SOURCE="$(cd "$(dirname "$0")" && pwd)"
TARGET="$(cd "$SOURCE/.." && pwd)"
FORCE=0
DRY_RUN=0

usage() {
  echo "Usage: bash ai-kit/install.sh [--target <project-root>] [--force] [--dry-run]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$(cd "$2" && pwd)"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$TARGET" != "$SOURCE" ]] || { echo "Target cannot be the kit directory." >&2; exit 2; }

PATHS=(AGENTS.md CLAUDE.md GEMINI.md ANTIGRAVITY.md .agents .ai .claude .cursor .githooks .windsurf .github/copilot-instructions.md .github/workflows/gates.yml)
FILES=()
for item in "${PATHS[@]}"; do
  source_path="$SOURCE/$item"
  [[ -e "$source_path" ]] || continue
  if [[ -d "$source_path" ]]; then
    while IFS= read -r -d '' file; do FILES+=("$file"); done < <(find "$source_path" -type f -print0)
  else
    FILES+=("$source_path")
  fi
done

CONFLICTS=0
for file in "${FILES[@]}"; do
  rel="${file#$SOURCE/}"
  dest="$TARGET/$rel"
  if [[ -f "$dest" ]] && ! cmp -s "$file" "$dest"; then
    echo "conflict: $rel" >&2
    CONFLICTS=1
  fi
done
if [[ "$CONFLICTS" -eq 1 && "$FORCE" -ne 1 ]]; then
  echo "Installation stopped: use --force to replace listed managed files." >&2
  exit 1
fi

for file in "${FILES[@]}"; do
  rel="${file#$SOURCE/}"
  dest="$TARGET/$rel"
  if [[ "$DRY_RUN" -eq 1 ]]; then echo "copy: $rel"; continue; fi
  mkdir -p "$(dirname "$dest")"
  cp "$file" "$dest"
done

if [[ "$DRY_RUN" -eq 0 ]]; then
  ignore="$TARGET/.gitignore"
  marker="# AI-Kit runtime state"
  if ! [[ -f "$ignore" ]] || ! grep -qF "$marker" "$ignore"; then
    printf '\n%s\n.ai-work/state/\n.ai-work/logs/\n.ai-work/snapshots/\n.ai-work/**/*.lock\n.ai-work/**/*.tmp\n' "$marker" >> "$ignore"
  fi
fi

echo "AI-Kit installed into $TARGET"
echo "Next: cd \"$TARGET\" && bash .ai/scripts/bootstrap.sh && bash .ai/scripts/doctor.sh"
