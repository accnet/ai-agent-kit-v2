#!/usr/bin/env bash
# AI-Kit Full Dispatch: dispatch → verify → approve → close
set -euo pipefail

TASK_ID="${1:?Usage: $0 TASK_ID RUNNER [REASON]}"
RUNNER="${2:?Usage: $0 TASK_ID RUNNER [REASON]}"
REASON="${3:-Auto-approved after successful verification}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_KIT="$SCRIPT_DIR/ai-kit"

echo "🚀 Dispatching $TASK_ID to $RUNNER..."
"$AI_KIT" dispatch "$TASK_ID" --runner "$RUNNER"

echo ""
echo "✅ Dispatch complete. Waiting 2s before verification..."
sleep 2

echo ""
echo "🔍 Verifying $TASK_ID..."
# `ai-kit verify` exits non-zero unless the report says passed (a FAIL, or an
# INCONCLUSIVE run where no functional check was configured at all). It used to
# exit 0 regardless, which made this guard a no-op: a task whose checks failed
# was auto-approved through QA and review and closed at `done`. The report is
# also re-read below so this stays correct even if the exit contract changes.
VERIFY_REPORT="$("$AI_KIT" verify "$TASK_ID")" || {
    echo "$VERIFY_REPORT"
    echo "❌ Verification did not pass. Stopping here (task stays at implementation-complete)."
    exit 1
}
echo "$VERIFY_REPORT"
if ! printf '%s' "$VERIFY_REPORT" | grep -q '"passed": true'; then
    echo "❌ Verification did not pass. Stopping here (task stays at implementation-complete)."
    exit 1
fi

echo ""
echo "✅ Verification passed. Proceeding to approvals..."

echo ""
echo "📋 QA approval for $TASK_ID..."
"$AI_KIT" approve "$TASK_ID" --role qa --reason "$REASON"

echo ""
echo "👀 Review approval for $TASK_ID..."
"$AI_KIT" approve "$TASK_ID" --role review --reason "$REASON"

echo ""
echo "🔒 Closing $TASK_ID..."
"$AI_KIT" transition "$TASK_ID" close --actor system --detail "Auto-closed by dispatch-full"

echo ""
echo "🎉 Task $TASK_ID complete!"
"$AI_KIT" status
