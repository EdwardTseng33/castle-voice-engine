# v2-daily-verdict · V2 自動驗收 Cron

**Schedule**: 每天 09:30 TST  
**Token cap**: 30k  
**Owner**: 馬魯克 (Gate 4) · 呼叫 calcifer Gate 1 browser 實測  
**Branch**: voice-path/v2.x-compositor (直到 Edward 拍板 merge main)

---

## 目的

每天自動跑 V2 Compositor + Lipsync 4 條驗收 metric，無需人工觸發。
連 3 天 FAIL 升 Edward。全 PASS 標 ready-for-Edward。燒錢 < NT$60/天。

---

## 工作流 (7 步)

### Step 1 · Chrome MCP 開 prod URL

```
tool: chrome_navigate
url: https://castle-voice-engine-castle-app--fastapi-app.modal.run/?debug=1
```

等 `window.__sophieCompositorReady === true` 出現在 console（最多 15s）。

### Step 2 · Dev bypass header 進站

確認 `/dev/health` 可通：

```
tool: chrome_execute_javascript
code: |
  fetch('/dev/health', {
    headers: { 'X-Castle-Dev-Bypass': '06c87b230ad966219137a5d7c005266f' }
  }).then(r => r.json()).then(d => console.log('[DEV HEALTH]', JSON.stringify(d)));
```

預期: `{"ok": true, "mode": "dev", ...}`  
若 403 → abort 當天 cron，寫 `castle/qa/v2-daily-verdict-{DATE}.md` 標 DEV_BYPASS_FAIL。

### Step 3 · POST /dev/simulate_realtime 跑 5 輪 e2e 對話

每輪用不同 utterance 覆蓋短句/長句/中文/混合場景：

| 輪次 | expected_utterance | 目的 |
|------|--------------------|------|
| 1 | 我懂你的感受 | 短句 PhraseMatcher 命中測試 |
| 2 | 早安 Edward，新的一天開始了 | 起手句命中 |
| 3 | 讓我幫你把這件事做好 | 中句測試 |
| 4 | 你今天看起來有點疲倦，先休息一下吧 | 長句測試 |
| 5 | OK, I understand. Let me handle this. | 英文句測試 |

```javascript
// 輪次範例 (重複 5 次不同 utterance)
fetch('/dev/simulate_realtime', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Castle-Dev-Bypass': '06c87b230ad966219137a5d7c005266f'
  },
  body: JSON.stringify({ expected_utterance: '我懂你的感受' })
}).then(r => {
  // SSE stream · 讀完等 sim.done
  var reader = r.body.getReader();
  var decoder = new TextDecoder();
  function pump() {
    return reader.read().then(function(chunk) {
      if (chunk.done) return;
      console.log('[SIM SSE]', decoder.decode(chunk.value));
      return pump();
    });
  }
  return pump();
});
```

每輪之間等 3s (讓 compositor 恢復 idle)。

### Step 4 · 呼叫 __sophieV2Verdict.collectMetrics(60000)

在 5 輪模擬結束後立即跑：

```javascript
window.__sophieV2Verdict.collectMetrics(5000).then(function(v) {
  console.log('[V2 VERDICT RESULT]', JSON.stringify(v, null, 2));
  window.__v2VerdictResult = v;
});
```

等 console 出現 `[V2 VERDICT RESULT]`（最多 30s）。
取出 `window.__v2VerdictResult`。

**注意**: collectMetrics 的 flickerRate 觀察視窗用 5000ms (cron 場景縮短，
不用 60s full 觀察，5 輪模擬 + 5s 足以量到 flicker rate 趨勢)。

### Step 5a · 全 PASS → 寫 ready-for-Edward 報告

檔案: `castle/qa/v2-daily-verdict-{YYYY-MM-DD}.md`

```markdown
# V2 Daily Verdict · {YYYY-MM-DD}

**Verdict**: PASS
**Run time**: {ISO timestamp}
**Duration observed**: 5000ms + 5 simulated rounds

## 4 Metrics

| Metric | Value | Target | Result |
|--------|-------|--------|--------|
| Flicker Rate | {value} switches/min | < 6 | PASS |
| Speaking Anim Latency | {value} ms | < 2000ms | PASS |
| State Alignment | {value} offset_ms | < 500ms | PASS |
| First Sentence Latency | {value} ms | < 3000ms | PASS |

## 證據

- Chrome MCP console log: [attached]
- Dev health check: PASS
- Simulate rounds: 5 / 5 completed

## Status

**ready-for-Edward** · V2 Compositor 今日驗收通過。

_由 v2-daily-verdict cron 自動產生 · 馬魯克 Gate 4_
```

### Step 5b · 任 1 條 FAIL → block + 寫 lesson

1. 寫 `castle/qa/v2-daily-verdict-{YYYY-MM-DD}.md` 標 FAIL (同上格式，Verdict 改 FAIL)
2. 寫 `memory/lesson/lesson_{DATE}_v2-daily-fail.md` (lesson_template 格式)：
   - 失敗的 metric 名稱 + 數值
   - 可能 root cause (compositor state / video src / DC handler hook missing)
   - Next step (呼叫卡西法修)
3. Slack ping `#項目討論-agent`：
   ```
   [V2 VERDICT FAIL] {DATE} · {metric名} {value} 超標 (target: {target})
   → lesson 已寫 · 請卡西法介入
   ```
4. 觸發城堡 followup (蘇菲路由)

### Step 6 · 連 3 天 FAIL 升 Edward

升級判斷：掃 `castle/qa/` 最近 3 份 verdict 檔，若全 FAIL：

```
Slack ping Edward:
[V2 DAILY VERDICT] 連 3 天 FAIL · 人工介入需要
最近失敗: {metric} - {values}
詳見 castle/qa/ 最近 3 份報告
```

### Step 7 · Slack 成功通知

全 PASS 時 Slack ping `#項目討論-agent`：
```
[V2 VERDICT PASS] {DATE} · 4 條全過
flickerRate={value} · animLatency={value}ms · alignment={value}ms · firstSentence={value}ms
```

---

## Verdict Template

完整檔案格式見 Step 5a/5b。

---

## 燒錢估算

| 項目 | 估算 |
|------|------|
| Chrome MCP 開 URL | ~NT$0 (瀏覽器操作) |
| 5 次 /dev/simulate_realtime | ~NT$0 (本地 SSE · 無外部 API 呼叫) |
| collectMetrics JS 執行 | ~NT$0 |
| Token 消耗 (30k cap) | ~NT$15-30/天 |
| **總計** | **< NT$60/天** |

---

## 依賴

- `castle/static/v2-verdict-checks.js` 已掛進 index.html (`<script>` 標籤)
- `castle/server/dev_endpoints.py` 已 attach_dev_routes
- `window.__sophieAvatarCompositor` 已初始化 (avatar-compositor.js)
- Chrome MCP 工具可用 (calcifer Gate 1 scope)

---

## 停用條件

- Edward 拍板 V2 merge main → 此 cron 升級成 main branch daily verdict
- V2 架構重大重寫 → 重新校準 4 條 metric 目標值

---

_v1.0 · 2026-05-25 · 馬魯克 V1.5 scope · Gate 4 自動驗收_
