#!/bin/bash
# scripts/edward-approve.sh · 2026-05-25 ship · Edward 親口拍板強制機制
#
# 用法：bash scripts/edward-approve.sh <commit_sha>
#
# 動作：寫 castle/qa/edward-approved-{full_sha}.ok
#       含：timestamp / sha / branch / 觸發者（蘇菲 daemon catch Edward「APPROVE {sha}」時呼叫）
#
# 紀律：deploy-prod.sh 強制 check 這個檔存在 · 不存在 → reject
#       唯一產生方式 = Edward 看過 staging URL 後親自 APPROVE
#       城堡 agent 不能擅自跑這個 script 給自己 approve

set -uo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

if [ $# -lt 1 ]; then
  echo "用法：bash scripts/edward-approve.sh <commit_sha>"
  echo "       sha 可以是 short (7+) 或 full (40)"
  exit 1
fi

INPUT_SHA="$1"
APPROVER="${APPROVER:-edward}"
SOURCE="${SOURCE:-manual-script}"

# Resolve to full SHA
RESOLVED=$(git rev-parse "$INPUT_SHA" 2>/dev/null || echo "")
if [ -z "$RESOLVED" ]; then
  # Allow approving a sha that's not in git yet (e.g. test-sha for dry-run)
  if [ ${#INPUT_SHA} -ge 7 ] && [ "$INPUT_SHA" != "${INPUT_SHA//[!a-zA-Z0-9-]/}" ]; then
    # Has non-alphanumeric (besides dash) - looks like test slug
    FULL_SHA="$INPUT_SHA"
    echo "⚠ git rev-parse 解不到 · 視為 test slug: $INPUT_SHA"
  else
    # Looks like sha-ish - allow as raw (test) but warn
    FULL_SHA="$INPUT_SHA"
    echo "⚠ git rev-parse 解不到 SHA · 仍寫檔 (test / 預先 approve scenario)"
  fi
else
  FULL_SHA="$RESOLVED"
fi

mkdir -p castle/qa

APPROVAL_FILE="castle/qa/edward-approved-${FULL_SHA}.ok"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

cat > "$APPROVAL_FILE" <<INNER
approval_timestamp: $TIMESTAMP
commit_sha: $FULL_SHA
input_arg: $INPUT_SHA
branch: $BRANCH
approver: $APPROVER
source: $SOURCE
note: Edward visual-approved staging URL · OK to promote prod
INNER

echo "✓ 寫入 $APPROVAL_FILE"
echo "---"
cat "$APPROVAL_FILE"
echo "---"
echo ""
echo "下一步：bash scripts/deploy-prod.sh"
exit 0
