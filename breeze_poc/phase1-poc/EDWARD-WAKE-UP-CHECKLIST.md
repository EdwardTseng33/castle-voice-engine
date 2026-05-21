# Edward 起床清單（Voice Path v2.0 PoC · Day 3 + Day 4）

> 卡西法 + 蘇菲 council 2026-05-22 凌晨 ship
> Branch: `voice-path/v2.0-breeze-poc`
> Edward 動作：`git pull` + 讀本檔 + 聽 2 個音檔 + 拍板 1 個選擇（< 5 min）

---

## 30 秒看懂

Day 3：BreezyVoice (台灣 MediaTek 開源 TTS) round-trip CER 86% / TTS P95 9.86s → **NO-GO（2 個 escalate trigger fired）**

蘇菲 council 自決 path：**BreezyVoice 暫 archive、Day 4 用 Edge TTS 暫代讓 Phase 1 demo 完整**、Edward 起床聽完整 demo + 拍板長期 path。

Day 4 結果：Edge TTS round-trip CER **24.33%** / TTS P95 **711ms** → **完勝 BreezyVoice 兩個關鍵軸**：

| 指標 | BreezyVoice (Day 3) | Edge TTS (Day 4) | 改善 |
|---|---|---|---|
| CER mean | 85.86% | **24.33%** | **3.5×** |
| TTS P95 | 9860 ms | **711 ms** | **14×** |
| 月費 | $30-50 | **$0** | 省 |

**蘇菲 + 卡西法推薦**：**Path A · Edge TTS 走、BreezyVoice archive**（Phase 2 voice clone 真要做時再修）。

---

## Edward 1 個拍板動作（< 5 min）

聽 2 個音檔判斷「聲音夠不夠用」：

| 步驟 | 動作 | 預期 |
|---|---|---|
| 1 | 雙擊 `phase1-poc/audio/t01-edge.wav`（Edge TTS 念「我今天早上跑了五公里...」）| 廣播級台灣腔女聲、自然 |
| 2 | 雙擊 `phase1-poc/audio/t01.wav`（BreezyVoice 同句對照）| 較粗糙、慢 |
| 3 | 雙擊 `phase1-poc/audio/castle_dispatch_response.wav`（Edge TTS 念 turnip 回應）| 完整一段「BeyondPath 2026-05-21 D1 retention 41.2 趴...」|

聽完後在 Slack `#項目討論-agent` 回 1 句：

| 回覆 | 卡西法接續動作 |
|---|---|
| **「Path A · Edge TTS 走」** | Phase 1 demo 用 Edge TTS、Phase 2-7 不修 BreezyVoice |
| **「Path B · 修 BreezyVoice」** | Day 5-6 卡西法修 hyperpyyaml + 換 bopomo 管線（24-48 hr ETA、修不一定成功）|
| **「Path C · 雙路並存」** | Edge TTS 預設 + BreezyVoice 留 voice clone 場景（~30 hr）|
| **「全 NO-GO 退」** | Phase 1 PoC archive、保留 OpenAI Realtime stack |

---

## Day 4 5 個 MUST 全 ship

| # | 檔 | Status |
|---|---|---|
| 1 | `phase1-poc/audio/t01-t10-edge.wav` (10 個 Edge TTS 音檔) | ✅ 10/10 |
| 2 | `phase1-poc/results/edge-vs-breezyvoice-comparison.md` | ✅ 完整對比 + 推薦 |
| 3 | `phase2-poc/eagle_enrollment_result.md` (Day 4 update) | ✅ pveagle 3.0.2 SDK 驗證 + API mapped |
| 4 | `CASTLE-DISPATCH-DEMO.md` (Day 4 update) + 真實 trace | ✅ turnip spec 真載入 + Edge TTS 真合成 + JSON trace |
| 5 | 本檔 `EDWARD-WAKE-UP-CHECKLIST.md` (Day 4 版、覆蓋 Day 3) | ✅ 你正在讀 |

額外 ship：
- `phase1-poc/results/edge-round-trip-cer.csv` (per-sentence CER 表)
- `phase1-poc/results/edge-latency.csv` (TTS / ASR P50/P95)
- `phase1-poc/results/edge-comparison-data.json` (machine-readable summary + Go/No-Go)
- `phase1-poc/results/castle_dispatch_real_trace.json` (端到端 trace)
- `phase1-poc/audio/castle_dispatch_response.wav` (turnip 回應 TTS)
- `castle_dispatch_demo.py` (端到端 demo script)
- `day4_edge.py` (Edge TTS round-trip script)

---

## Day 4 為什麼選 Edge TTS（蘇菲 council 自決理由）

1. **BreezyVoice 修不一定成功**：CER 86% 根因可能是 cosyvoice 0.x fallback path + voice clone prompt noise + Modal A10G cold start，修要 24-48 hr 且結果不確定
2. **Edge TTS 業界常用**：sulima 5/22 已 Tier B 評過、Microsoft 官方 zh-TW-HsiaoChenNeural、無 API key、零月費、本機跑
3. **Phase 1 demo 不該被 BreezyVoice 卡死**：Phase 1 主目標是「ASR + TTS + 派工 chain」整體通、不是「voice clone Edward」（那是 Phase 2 議題）
4. **Edward 5/22 拍板「持續推進」**：不要 silent 卡死、給能聽的 demo

---

## 1 分鐘 quick verify（不必動）

| 檢查 | 在哪看 | 預期 |
|---|---|---|
| Edge TTS 10 句 | `audio/t01-t10-edge.wav` | 10 個 WAV、檔案大小 23-31 KB |
| Edge vs BV CER 對比 | `results/edge-vs-breezyvoice-comparison.md` | TL;DR 表 + per-sentence 細表 |
| Edge round-trip CER | `results/edge-round-trip-cer.csv` | mean 24.33% / median 25.84% |
| Edge TTS 延遲 | `results/edge-latency.csv` | P50 489ms / P95 711ms |
| 城堡派工 trace | `results/castle_dispatch_real_trace.json` | 完整 4 階段 / total 1432ms |
| Eagle SDK 驗證 | `phase2-poc/eagle_enrollment_result.md` | pveagle 3.0.2 install OK / API mapped / await AccessKey |
| 城堡派工音檔 | `audio/castle_dispatch_response.wav` | 1 個 WAV、念 turnip 結論 |

---

## 卡西法雙軌工時校準（Day 4）

- **預估**：Day 4 = 4 hr（資深工程師、AI 輔助、含 Edge TTS 驗證 + Eagle SDK 測試 + dispatch trace + 報告）
- **移動城堡**：卡西法 ~2-3 hr 自治推進（heredoc quoting 反覆撞 PowerShell parser 燒了 ~30 min、其他都順）
- **倍率**：~0.5-0.75×（Day 4 比 Day 3 順、因為架構已熟、Edge TTS 立刻 work）

---

## 反 silent ended 證據（5/22 凌晨 SOP 對齊）

- ✅ 每 stage 完 commit（4 個 commit）：8d6e45c / 4e9a5ba / 7485225 / 2c75479 / 36f952c
- ✅ Modal 累計 cost < $1（只跑 ASR、沒重建 image）
- ✅ castle/main 零污染（全 work on `voice-path/v2.0-breeze-poc` branch）
- ✅ 沒撞牆（Edge TTS 一次就 work）
- ✅ 全 stage 真實跑、不 mock（除 Stage 2 + 3 dispatch demo 因無 ANTHROPIC_API_KEY 明標 simulated）

---

## Edward 起床 4 步動作 summary

1. 1 min · `git pull` + 讀本檔（你正在做）
2. 2 min · 雙擊聽 `t01-edge.wav` + `t01.wav` + `castle_dispatch_response.wav`
3. 30 sec · Slack `#項目討論-agent` 回 Path A / B / C / 退
4. （可選 1 min · 拿 Picovoice AccessKey 貼 `.env` 啟動 Phase 2 Eagle）

卡西法收到 Path 拍板立刻接 Day 5。

---

*Day 4 終版 · 2026-05-22 · 卡西法 + 蘇菲 council 自治 · Edward 起床 < 5 min 拍板長期 path · 全 5 MUST + 7 額外 artifact ship*
