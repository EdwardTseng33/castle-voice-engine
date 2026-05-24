#!/bin/bash
# scripts/deploy-prod.sh · 2026-05-25 ship · Edward 親口拍板強制機制
#
# 用法：bash scripts/deploy-prod.sh
#
# 強制守門：
#   只接受 git rev-parse HEAD = castle/qa/edward-approved-{full_sha}.ok 存在
#   不存在 → exit 1 + 告訴你「先 deploy-staging.sh + Edward APPROVE」
#   存在 → modal deploy app.py
#
# 紀律：城堡所有 agent 禁止直接 modal deploy app.py
#       prod 必走這 script · 必經 Edward visual approval
#
# 設計：守門 logic 寫死 bash · 不靠 cognitive 紀律 · 不可繞過

set -uo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# Allow optional override SHA (for retry / explicit promote)
TARGET_SHA="${1:-}"
if [ -z "$TARGET_SHA" ]; then
  TARGET_SHA=$(git rev-parse HEAD)
fi

# Normalize to full SHA if short was passed
if [ ${#TARGET_SHA} -lt 40 ]; then
  RESOLVED=$(git rev-parse "$TARGET_SHA" 2>/dev/null || echo "")
  if [ -z "$RESOLVED" ]; then
    echo "🔴 無法解析 SHA: $TARGET_SHA"
    exit 1
  fi
  TARGET_SHA="$RESOLVED"
fi

SHORT_SHA=$(git rev-parse --short "$TARGET_SHA" 2>/dev/null || echo "$TARGET_SHA")
BRANCH=$(git rev-parse --abbrev-ref HEAD)
APPROVAL_FILE="castle/qa/edward-approved-${TARGET_SHA}.ok"

echo "==========================================="
echo "🚀  Deploy PROD · castle-voice-engine"
echo "  repo:   $REPO_ROOT"
echo "  branch: $BRANCH"
echo "  SHA:    $SHORT_SHA  ($TARGET_SHA)"
echo "==========================================="

# 0. Working tree must be clean (prod 不允許帶未 commit 改動)
DIRTY=$(git status --porcelain | wc -l | tr -d ' ')
if [ "$DIRTY" -gt 0 ]; then
  echo ""
  echo "🔴 prod deploy reject · working tree 有 $DIRTY 個未 commit 改動"
  echo "    先 git commit 把改動入庫 → 走 deploy-staging.sh 重跑 → Edward APPROVE → deploy-prod.sh"
  echo "    (prod 部署的 SHA 必須跟 git 對得起來 · 不接 dirty state)"
  exit 1
fi

# 1. Approval gate
echo ""
echo "[1/2] 守門 · Edward visual approval"
if [ ! -f "$APPROVAL_FILE" ]; then
  echo "  ✗ 缺 approval file: $APPROVAL_FILE"
  echo ""
  echo "🔴 prod deploy reject · 缺 Edward visual approval for $SHORT_SHA"
  echo ""
  echo "正確流程："
  echo "  1. bash scripts/deploy-staging.sh"
  echo "  2. Edward 試 staging URL"
  echo "  3. Edward reply 「APPROVE $TARGET_SHA」"
  echo "  4. bash scripts/edward-approve.sh $TARGET_SHA"
  echo "  5. bash scripts/deploy-prod.sh"
  echo ""
  echo "(approval file 路徑：$APPROVAL_FILE)"
  exit 1
fi
echo "  ✓ approval file 存在: $APPROVAL_FILE"
echo "  ✓ 內容："
sed 's/^/      /' "$APPROVAL_FILE"

# 2. Modal deploy
echo ""
echo "[2/2] Modal deploy app.py ..."
echo "-------------------------------------------"
python -m modal deploy app.py
DEPLOY_EXIT=$?
echo "-------------------------------------------"

echo ""
echo "==========================================="
if [ $DEPLOY_EXIT -ne 0 ]; then
  echo "🔴 modal deploy failed · exit $DEPLOY_EXIT"
  exit 1
fi

echo "🟢 PROD deployed"
echo "  SHA:    $SHORT_SHA  ($TARGET_SHA)"
echo "  branch: $BRANCH"
echo "==========================================="
echo ""
echo "建議下一步："
echo "  - bash scripts/pre-ship-verify.sh   (跑 prod 完整自動驗收)"
echo "  - 通報 Edward「v$(git describe --tags --abbrev=0 2>/dev/null || echo $SHORT_SHA) 已 promote prod」"
exit 0
