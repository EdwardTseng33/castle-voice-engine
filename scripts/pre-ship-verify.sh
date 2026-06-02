#!/bin/bash
# pre-ship-verify.sh · v0.8.2 起立 · 蘇菲 ship 前 mechanical enforcement
# Edward 2026-05-23 親口要求「交接驗收前你們自己跑一次」紀律
# 違反 = ship blocked (exit 1)
#
# 跑法：bash scripts/pre-ship-verify.sh
# 跑時機：每次 `python -m modal deploy app.py` 完成後立刻跑
# 過完才能報 Edward「上線完成」

URL="${1:-https://edwardt0303--castle-voice-engine-fastapi-app.modal.run}"
FAIL=0

# v0.9.6+ · 抓 verify cookie (Google OAuth gate 啟用後 /static/* 必認)
# 用 Edward email 簽一個 verify cookie 給 curl 帶
VERIFY_COOKIE=$(python -c "
from itsdangerous import URLSafeTimedSerializer
import os
secret = os.environ.get('SOPHIE_COOKIE_SECRET', 'a7f9c2e4d8b1a3c5e7f0b2d4a6c8e1b3d5f7a9c2e4b6d8f0a2c4e6b8d1f3a5c7')
s = URLSafeTimedSerializer(secret, salt='sophie-auth-cookie-v1')
print(s.dumps('edwardt0303@gmail.com'))
" 2>/dev/null)

if [ -z "$VERIFY_COOKIE" ]; then
  echo "⚠ verify cookie mint 失敗 · 跳過 auth-gated 檢查 (auth gate 必過、Edward 自己驗)"
  COOKIE_HEADER=""
else
  COOKIE_HEADER="-H Cookie:sophie_auth=$VERIFY_COOKIE"
fi

echo "==========================================="
echo "🛡  Voice Path Pre-Ship Verify (v1.1.0 · v0.9.6 auth gate aware)"
echo "  URL: $URL"
echo "==========================================="

check_endpoint() {
  local PATH_REL="$1"
  local LABEL="$2"
  local CODE=$(curl -s -o /dev/null -w '%{http_code}' $COOKIE_HEADER "$URL$PATH_REL")
  if [ "$CODE" = "200" ]; then
    echo "✓ $LABEL ($CODE)"
  else
    echo "✗ $LABEL ($CODE) · BLOCKER"
    FAIL=1
  fi
}

check_auth_gate() {
  # 確認 /static/* 沒 cookie 會被擋 (307 redirect to auth.html) — v0.9.6 紀律
  local PATH_REL="$1"
  local LABEL="$2"
  local CODE=$(curl -s -o /dev/null -w '%{http_code}' "$URL$PATH_REL")
  if [ "$CODE" = "307" ] || [ "$CODE" = "302" ]; then
    echo "✓ $LABEL · 沒 cookie 被擋 ($CODE) · auth gate work"
  elif [ "$CODE" = "200" ]; then
    echo "✗ $LABEL · 沒 cookie 居然 200 通過 · auth gate 漏洞 · BLOCKER"
    FAIL=1
  else
    echo "⚠ $LABEL · 沒 cookie 回 $CODE (預期 307) · 可能 auth gate 異常"
  fi
}

check_static_public() {
  # v1.2.0 訪客模式 · /static/* 應公開 (沒 cookie 也 200)
  local PATH_REL="$1"
  local LABEL="$2"
  local CODE=$(curl -s -o /dev/null -w '%{http_code}' "$URL$PATH_REL")
  if [ "$CODE" = "200" ]; then
    echo "✓ $LABEL · 訪客模式 (沒 cookie 也通) ($CODE)"
  else
    echo "✗ $LABEL · 沒 cookie 卻 $CODE (預期 200) · 訪客模式破 · BLOCKER"
    FAIL=1
  fi
}

check_api_gate() {
  # v1.2.0 訪客模式 · API endpoints (/sdp /camera /vision /memory /tavus /session /personas) 仍守
  # 沒 cookie 應 401 (擋下訪客 · 防別人燒 OpenAI / Anthropic cost + 隱私)
  local PATH_REL="$1"
  local LABEL="$2"
  local METHOD="${3:-GET}"
  local CODE
  if [ "$METHOD" = "POST" ]; then
    CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL$PATH_REL")
  else
    CODE=$(curl -s -o /dev/null -w '%{http_code}' "$URL$PATH_REL")
  fi
  if [ "$CODE" = "401" ]; then
    echo "✓ $LABEL · API gate 守得住 ($CODE 未授權)"
  elif [ "$CODE" = "200" ]; then
    echo "✗ $LABEL · 沒 cookie 居然 200 通過 · API gate 漏洞 · BLOCKER (防燒錢/防隱私)"
    FAIL=1
  elif [ "$CODE" = "307" ] || [ "$CODE" = "302" ]; then
    echo "⚠ $LABEL · 回 $CODE (預期 401 直接拒) · 可能 middleware 設定漏 · 請查"
  else
    echo "⚠ $LABEL · 沒 cookie 回 $CODE (預期 401) · 行為非預期"
  fi
}

check_range() {
  local PATH_REL="$1"
  local LABEL="$2"
  local CODE=$(curl -s -o /dev/null -w '%{http_code}' $COOKIE_HEADER -H "Range: bytes=0-1023" "$URL$PATH_REL")
  if [ "$CODE" = "206" ]; then
    echo "✓ $LABEL Range 支援 ($CODE Partial)"
  else
    echo "✗ $LABEL Range fail ($CODE · 預期 206) · video 不能 streaming play"
    FAIL=1
  fi
}

echo ""
echo "[0/5] 公開端點 (v1.2.0 訪客模式 · /static/* 全公開)"
check_endpoint "/health" "/health"
check_static_public "/static/auth.html" "/static/auth.html (login page)"
check_static_public "/static/index.html" "/static/index.html"
check_static_public "/static/sophie-idle.mp4" "/static/sophie-idle.mp4"
check_static_public "/static/sw.js" "/static/sw.js"
check_static_public "/static/manifest.json" "/static/manifest.json"

echo ""
echo "[0.5/5] API gate 守得住 (v1.2.0 訪客模式 · API 仍認證 · 防燒錢/防隱私)"
check_api_gate "/sdp" "/sdp" POST
check_api_gate "/camera/enable" "/camera/enable" POST
check_api_gate "/vision/emotion_latest" "/vision/emotion_latest"
check_api_gate "/memory/summarize" "/memory/summarize" POST
check_api_gate "/tavus/start" "/tavus/start" POST

echo ""
echo "[1/5] 主介面檔 (帶 verify cookie)"
check_endpoint "/static/index.html" "index.html"
check_endpoint "/static/manifest.json" "manifest.json"
check_endpoint "/static/sw.js" "sw.js"
check_endpoint "/static/animation-pool.js" "animation-pool.js"

echo ""
echo "[2/5] SW cache 版本"
SW_VER=$(curl -s $COOKIE_HEADER "$URL/static/sw.js" | grep "CACHE_VERSION =" | head -1 | sed -E "s/.*'(.*)'.*/\1/")
echo "  SW CACHE_VERSION = $SW_VER"

# v2.1.0 . calcifer 6/2 . VER discipline check (Edward 6/2 catch: shipped without bumping VER)
#   4 version strings must agree: debug overlay VER / animation-pool ?v= / SW CACHE_VERSION / modal vm-version
echo ""
echo "[2b/5] discipline . version string consistency (Edward 6/2 catch)"
IDX=$(curl -s $COOKIE_HEADER "$URL/static/index.html")
VER_OVERLAY=$(echo "$IDX" | grep -oE 'VER [0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.-]*' | head -1 | sed 's/^VER //; s/^v//')
VER_POOL=$(echo "$IDX" | grep -oE 'animation-pool\.js\?v=[A-Za-z0-9.-]+' | head -1 | sed -E 's/.*v=//; s/^v//')
VER_MODAL=$(echo "$IDX" | grep -oE 'class="vm-version">v[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.-]*<' | head -1 | sed -E 's/.*>v//; s/<.*//')
SW_VER_PLAIN=$(echo "$SW_VER" | sed 's/^v//')
echo "  debug overlay  VER = ${VER_OVERLAY:-<none>}"
echo "  animation-pool ?v= = ${VER_POOL:-<none>}"
echo "  modal vm-version   = ${VER_MODAL:-<none>}"
echo "  SW CACHE_VERSION   = ${SW_VER_PLAIN:-<none>}"
if [ "$VER_OVERLAY" = "$VER_POOL" ] && [ "$VER_OVERLAY" = "$VER_MODAL" ] && [ "$VER_OVERLAY" = "$SW_VER_PLAIN" ]; then
  echo "OK 4 version strings agree ($VER_OVERLAY)"
else
  echo "FAIL version strings disagree . code changed without bumping VER (Edward 6/2 discipline) . align then deploy"
  FAIL=1
fi

echo ""
echo "[3/5] 4 個動畫狀態 mp4 reachable + Range 支援"
for STATE in idle speaking task-received task-handoff; do
  check_endpoint "/static/sophie-$STATE.mp4" "sophie-$STATE.mp4"
  check_range "/static/sophie-$STATE.mp4" "sophie-$STATE.mp4"
done

echo ""
echo "[4/5] HTML content 自我檢查"
HTML=$(curl -s $COOKIE_HEADER "$URL/static/index.html")
echo "$HTML" | grep -q "蘇菲" && echo "✓ HTML 含蘇菲名" || { echo "✗ HTML 缺蘇菲名"; FAIL=1; }
echo "$HTML" | grep -q "sophie-idle.mp4" && echo "✓ HTML video src=sophie-idle.mp4" || { echo "✗ HTML video src 錯"; FAIL=1; }
echo "$HTML" | grep -q "sophie-portrait.png" && { echo "✗ HTML 還有 poster=sophie-portrait.png (v0.8.1 已砍 · 應該不存在)"; FAIL=1; } || echo "✓ HTML 無舊 poster fallback"
echo "$HTML" | grep -q "animation-pool.js" && echo "✓ HTML mount animation-pool.js" || { echo "✗ HTML 缺 animation-pool.js script"; FAIL=1; }
echo "$HTML" | grep -q "versionTrigger" && echo "✓ HTML 含版本資訊 i 圖示 (v0.7.3 info modal)" || echo "⚠ HTML 缺 versionTrigger"

echo ""
echo "[5/5] 紀律 · changelog 同步檢查 (Edward 5/23 17:50 catch)"
# 抓最近 N 個真實功能 commit 版本 (跳過 "SW vX.Y.Z bump" 只 cache 版號類)
# 過濾掉非實 ship 類 (SW cache bump · docs spec drop · implement report)
RECENT_COMMITS=$(cd "C:/Users/Administrator/Claude/castle-voice-engine" 2>/dev/null && \
  git log --oneline -20 | \
  grep -vE '^[a-f0-9]+ SW v[0-9]' | \
  grep -vE '^[a-f0-9]+ docs ' | \
  grep -vE '^[a-f0-9]+ v[0-9.]+ implement report' | \
  grep -oE 'v[0-9]+\.[0-9]+(\.[0-9]+){1,2}' | head -3)
HTML_VERSIONS=$(echo "$HTML" | grep -oE 'class="vm-entry-ver">v[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?<' | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?')
for VER in $RECENT_COMMITS; do
  if echo "$HTML_VERSIONS" | grep -q "^$VER\$"; then
    echo "✓ Changelog 含 $VER"
  else
    echo "⚠ Changelog 缺 $VER (commit 有但 modal 沒同步 · 須更新版本資訊彈窗)"
    FAIL=1
  fi
done

echo ""
echo "==========================================="
if [ $FAIL -eq 0 ]; then
  echo "🟢 PASS · Edward 可以打開試"
  echo "==========================================="
  echo ""
  echo "已知限制 (chrome MCP 後台 tab 驗不到、Edward 真實前景驗)："
  echo "- video element 真實 load + play (autoplay policy 後台 tab 擋)"
  echo "- GPT realtime tools function call emit 真實流"
  echo "- 麥克風 user gesture 真實 grant"
  echo ""
  echo "Edward 驗收 checklist (報 Edward 時附這 5 條)："
  echo "  1. Ctrl+Shift+R 強制刷新清舊 cache"
  echo "  2. 看到蘇菲 Vidu 編辮露肩 video loop 真實播放"
  echo "  3. 點 Start video chat 綠鈕 + 給麥克風權限"
  echo "  4. 講「妳好蘇菲」聽到 marin 中文聲音真即時回答"
  echo "  5. 蘇菲講話期間 video 切到 speaking state、講完回 idle"
  exit 0
else
  echo "🔴 FAIL · ship blocked · 不報 Edward 完成"
  echo "==========================================="
  exit 1
fi
