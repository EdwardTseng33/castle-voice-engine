#!/bin/bash
# scripts/deploy-staging.sh · 2026-05-25 ship · Edward 親口拍板強制機制
#
# 用法：bash scripts/deploy-staging.sh
#
# 動作：
#   1. 確認 working tree 乾淨 + 抓當前 commit SHA
#   2. modal deploy app_staging.py
#   3. 跑 4 條 staging 自動驗收（health / index.html / lipsync manifest / auth gate）
#   4. 任一 fail → exit 1（避免城堡 ship 廢品到 staging）
#   5. 全 pass → print staging URL + commit SHA + Edward APPROVE 指引
#
# 紀律：城堡 ship 必先進 staging · prod deploy 必經 Edward APPROVE {sha}

set -uo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
STAGING_URL="${STAGING_URL:-https://edwardt0303--castle-voice-engine-staging-fastapi-app.modal.run}"

echo "==========================================="
echo "🚧  Deploy STAGING · castle-voice-engine-staging"
echo "  repo: $REPO_ROOT"
echo "==========================================="

# 1. Working tree / branch / SHA
DIRTY=$(git status --porcelain | wc -l | tr -d ' ')
COMMIT_SHA=$(git rev-parse --short HEAD)
FULL_SHA=$(git rev-parse HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo ""
echo "[1/4] Git state"
echo "  branch: $BRANCH"
echo "  HEAD:   $COMMIT_SHA  ($FULL_SHA)"
if [ "$DIRTY" -gt 0 ]; then
  echo "  ⚠ working tree 有 $DIRTY 個未 commit 改動 · staging 跑當前 HEAD · 之後須 commit 才能 promote prod"
fi

# 2. Modal deploy
echo ""
echo "[2/4] Modal deploy app_staging.py ..."
echo "-------------------------------------------"
python -m modal deploy app_staging.py
DEPLOY_EXIT=$?
echo "-------------------------------------------"
if [ $DEPLOY_EXIT -ne 0 ]; then
  echo ""
  echo "🔴 modal deploy failed · exit $DEPLOY_EXIT"
  exit 1
fi

# 3. Mint verify cookie (Edward email) for /static/* + auth-gated checks
VERIFY_COOKIE=$(python -c "
from itsdangerous import URLSafeTimedSerializer
import os
secret = os.environ.get('SOPHIE_COOKIE_SECRET', 'a7f9c2e4d8b1a3c5e7f0b2d4a6c8e1b3d5f7a9c2e4b6d8f0a2c4e6b8d1f3a5c7')
s = URLSafeTimedSerializer(secret, salt='sophie-auth-cookie-v1')
print(s.dumps('edwardt0303@gmail.com'))
" 2>/dev/null)

if [ -z "$VERIFY_COOKIE" ]; then
  COOKIE_HEADER=""
  echo "⚠ verify cookie mint 失敗 · /static 檢查可能跑 401"
else
  COOKIE_HEADER="-H Cookie:sophie_auth=$VERIFY_COOKIE"
fi

# 4. 4-pack auto verify
echo ""
echo "[3/4] Staging 自動驗收 (4 條)"
FAIL=0

# 4a. /health 200
HEALTH_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$STAGING_URL/health")
if [ "$HEALTH_CODE" = "200" ]; then
  echo "  ✓ /health → 200"
else
  echo "  ✗ /health → $HEALTH_CODE  (expect 200)"
  FAIL=1
fi

# 4b. /static/index.html 200 + contains AvatarCompositor / index script tag
INDEX_BODY=$(curl -s $COOKIE_HEADER "$STAGING_URL/static/index.html")
INDEX_CODE=$(curl -s -o /dev/null -w '%{http_code}' $COOKIE_HEADER "$STAGING_URL/static/index.html")
if [ "$INDEX_CODE" = "200" ]; then
  echo "  ✓ /static/index.html → 200"
else
  echo "  ✗ /static/index.html → $INDEX_CODE"
  FAIL=1
fi
# Check for any expected script tag (AvatarCompositor or animation-pool.js)
if echo "$INDEX_BODY" | grep -qE 'AvatarCompositor|animation-pool\.js|<script'; then
  echo "  ✓ index.html 含 script tag (AvatarCompositor / animation-pool / 其他)"
else
  echo "  ✗ index.html 缺 script tag · 主介面壞"
  FAIL=1
fi

# 4c. /lipsync/manifest.json 200 + phrases array
MANIFEST_BODY=$(curl -s $COOKIE_HEADER "$STAGING_URL/lipsync/manifest.json")
MANIFEST_CODE=$(curl -s -o /dev/null -w '%{http_code}' $COOKIE_HEADER "$STAGING_URL/lipsync/manifest.json")
if [ "$MANIFEST_CODE" = "200" ]; then
  echo "  ✓ /lipsync/manifest.json → 200"
else
  echo "  ✗ /lipsync/manifest.json → $MANIFEST_CODE"
  FAIL=1
fi
PHRASES_COUNT=$(echo "$MANIFEST_BODY" | python -c "import sys, json
try:
    d = json.loads(sys.stdin.read())
    arr = d.get('phrases', []) if isinstance(d, dict) else []
    print(len(arr))
except Exception:
    print(-1)
")
if [ "$PHRASES_COUNT" -gt 0 ] 2>/dev/null; then
  echo "  ✓ lipsync manifest phrases.length = $PHRASES_COUNT"
else
  echo "  ⚠ lipsync manifest phrases.length = $PHRASES_COUNT  (staging volume 還沒灌 mp4 · 不 fail)"
fi

# 4d. /auth/whoami 401 (no cookie)
WHOAMI_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$STAGING_URL/auth/whoami")
if [ "$WHOAMI_CODE" = "401" ]; then
  echo "  ✓ /auth/whoami (no cookie) → 401"
else
  echo "  ✗ /auth/whoami (no cookie) → $WHOAMI_CODE  (expect 401)"
  FAIL=1
fi

# 5. Verdict
echo ""
echo "==========================================="
if [ $FAIL -ne 0 ]; then
  echo "🔴 STAGING auto-verify FAIL · ship blocked"
  echo "    城堡別把廢品丟給 Edward 試 · 先修再 deploy-staging.sh 一次"
  exit 1
fi

echo "🟢 STAGING ready"
echo "  URL:    $STAGING_URL"
echo "  SHA:    $COMMIT_SHA  ($FULL_SHA)"
echo "  branch: $BRANCH"
echo "==========================================="
echo ""
echo "下一步（蘇菲彙報給 Edward）："
echo "  1. 把 $STAGING_URL 丟給 Edward"
echo "  2. Edward 自己打開試 1 分鐘"
echo "  3. 過 → reply 「APPROVE $FULL_SHA」"
echo "  4. 蘇菲跑 bash scripts/edward-approve.sh $FULL_SHA"
echo "  5. 通過後才 bash scripts/deploy-prod.sh"
echo ""
echo "  不過 → Edward 講要改什麼 · 城堡修完再 deploy-staging.sh 一次"
exit 0
