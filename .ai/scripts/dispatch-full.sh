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
if ! "$AI_KIT" verify "$TASK_ID"; then
    echo "❌ Verification failed. Stopping here."
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
