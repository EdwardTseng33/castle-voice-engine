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

echo "==========================================="
echo "🛡  Voice Path Pre-Ship Verify"
echo "  URL: $URL"
echo "==========================================="

check_endpoint() {
  local PATH_REL="$1"
  local LABEL="$2"
  local CODE=$(curl -s -o /dev/null -w '%{http_code}' "$URL$PATH_REL")
  if [ "$CODE" = "200" ]; then
    echo "✓ $LABEL ($CODE)"
  else
    echo "✗ $LABEL ($CODE) · BLOCKER"
    FAIL=1
  fi
}

check_range() {
  local PATH_REL="$1"
  local LABEL="$2"
  local CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Range: bytes=0-1023" "$URL$PATH_REL")
  if [ "$CODE" = "206" ]; then
    echo "✓ $LABEL Range 支援 ($CODE Partial)"
  else
    echo "✗ $LABEL Range fail ($CODE · 預期 206) · video 不能 streaming play"
    FAIL=1
  fi
}

echo ""
echo "[1/4] 主介面檔"
check_endpoint "/static/index.html" "index.html"
check_endpoint "/static/manifest.json" "manifest.json"
check_endpoint "/static/sw.js" "sw.js"
check_endpoint "/static/animation-pool.js" "animation-pool.js"

echo ""
echo "[2/4] SW cache 版本"
SW_VER=$(curl -s "$URL/static/sw.js" | grep "CACHE_VERSION =" | head -1 | sed -E "s/.*'(.*)'.*/\1/")
echo "  SW CACHE_VERSION = $SW_VER"

echo ""
echo "[3/4] 4 個動畫狀態 mp4 reachable + Range 支援"
for STATE in idle speaking task-received task-handoff; do
  check_endpoint "/static/sophie-$STATE.mp4" "sophie-$STATE.mp4"
  check_range "/static/sophie-$STATE.mp4" "sophie-$STATE.mp4"
done

echo ""
echo "[4/4] HTML content 自我檢查"
HTML=$(curl -s "$URL/static/index.html")
echo "$HTML" | grep -q "蘇菲" && echo "✓ HTML 含蘇菲名" || { echo "✗ HTML 缺蘇菲名"; FAIL=1; }
echo "$HTML" | grep -q "sophie-idle.mp4" && echo "✓ HTML video src=sophie-idle.mp4" || { echo "✗ HTML video src 錯"; FAIL=1; }
echo "$HTML" | grep -q "sophie-portrait.png" && { echo "✗ HTML 還有 poster=sophie-portrait.png (v0.8.1 已砍 · 應該不存在)"; FAIL=1; } || echo "✓ HTML 無舊 poster fallback"
echo "$HTML" | grep -q "animation-pool.js" && echo "✓ HTML mount animation-pool.js" || { echo "✗ HTML 缺 animation-pool.js script"; FAIL=1; }
echo "$HTML" | grep -q "Sophie · AI Companion" && echo "✓ HTML 含新 watermark" || echo "⚠ HTML 缺 Sophie · AI Companion watermark (女巫 v0.7.3 spec 待 implement OK)"

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
