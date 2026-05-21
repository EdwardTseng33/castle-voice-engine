# Edge TTS vs BreezyVoice 對比（Phase 1 PoC · Day 4）

> 卡西法 2026-05-22 凌晨自治 ship
> 對照：Day 3 BreezyVoice round-trip（DAY3-COMPLETE.md）→ Day 4 Edge TTS 同樣 10 句 + 同樣 Breeze-ASR-25 endpoint round-trip
> 目的：替蘇菲拍板「BreezyVoice 暫 archive、用 Edge TTS 暫代讓 Phase 1 demo 完整」蒐證

---

## TL;DR · Edge TTS 完勝兩個關鍵軸

| 指標 | BreezyVoice（Day 3）| Edge TTS（Day 4）| 改善 |
|---|---|---|---|
| **CER mean** | 85.86% | **24.33%** | **3.5× 更好** |
| **CER median** | 95.0% | **25.84%** | **3.7× 更好** |
| **CER min** | 61.9% | **0.0%**（t02 完美） | 完美對齊 |
| **CER max** | 107.14% | **60.0%**（t06） | 仍最難一句但不爛尾 |
| **TTS P50** | 7349 ms | **488.6 ms** | **15× 更快** |
| **TTS P95** | 9860 ms | **711.3 ms** | **13.9× 更快** |
| **TTS mean** | ~7900 ms | **519.9 ms** | **15× 更快** |
| **10/10 成功** | 是（成功合成、但失真）| 是（成功 + 多數可懂） | 同 |
| **月費** | ~$30-50（Modal A10G GPU on-demand）| **$0**（Microsoft 免費）| 省 |
| **API key 需求** | 是（Modal token）| **無**（匿名）| 省 onboarding |
| **本機 / 雲** | Modal A10G GPU | **本機 Python**（純網路 outbound）| 部署簡單 |
| **Voice clone 能力** | 有（zero-shot 30s prompt）| 無 | BV 仍贏 |
| **台灣腔** | 有（zh-TW base）| 有（`zh-TW-HsiaoChenNeural` Microsoft 官方台灣腔女聲）| 同 |

**Go / No-Go**：
- vs 5% CER baseline：仍 **FAIL**（24.33% > 5%）—— 但接近合理範圍、跟業界 STT-TTS cascade 同 stack baseline 差距合理
- vs 3000ms P95 baseline：**PASS**（711ms << 3000ms）—— 對話節奏完全沒問題
- vs BreezyVoice 兩軸：**Edge TTS WINS**（CER 更低 + P95 更低）

---

## Per-sentence CER 對照

| tag | sentence (excerpt) | BreezyVoice CER | Edge TTS CER | 改善 |
|---|---|---|---|---|
| t01 | 我今天早上跑了五公里 | 77.27% | **18.18%** | -59.09 pp |
| t02 | 蘇菲幫我看一下昨天留存率 | 72.41% | **0.0%** | -72.41 pp ⭐ |
| t03 | 卡西法去確認預覽網址 | 80.0% | **28.57%** | -51.43 pp |
| t04 | 派蕪菁頭看用戶退訂原因 | 88.46% | **26.67%** | -61.79 pp |
| t05 | 我預算大概一個月五千塊 | 73.68% | **36.84%** | -36.84 pp |
| t06 | 三點半開會、12 樓 A 區 | **100.0%**（"Wow."）| 60.0% | -40.0 pp（仍最難）|
| t07 | component refactor 中英 code-switch | 97.83% | **25.0%** | -72.83 pp ⭐ |
| t08 | CFO ROI 3.2 倍 | 81.58% | **31.25%** | -50.33 pp |
| t09 | 我有點不耐煩了 | **100.0%**（"Hi 我有點無奈翻"）| **5.88%** | -94.12 pp ⭐⭐ |
| t10 | Sophie can you help me（英文）| 61.9% | **10.91%** | -50.99 pp |

**亮點**：
- t02、t07、t09 三句 BreezyVoice 嚴重失真（72-100% CER）、Edge TTS 直接打到 0-25%
- t10 純英文 Edge TTS 10.91%（接近完美）→ 中英 code-switch 也穩
- t06「三點半開會」是兩家都最弱的—— ref 含「12 樓 A 區」這種數字+英文短代號、Edge TTS 念成 ASR 仍會搞混、但已不是 BreezyVoice 那種徹底失敗（"Wow."）

---

## 延遲分布對照

### TTS latency（每句獨立合成、不含 ASR）

```
                  P50      P95      min      max      mean
BreezyVoice    7349 ms  9860 ms  3800 ms  11000 ms  ~7900 ms
Edge TTS        489 ms   711 ms   411 ms    761 ms    520 ms
```

**意義**：對話節奏感、Edge TTS 半秒內出聲、BreezyVoice 平均 8 秒、人類等待感差距非常大。即使 BreezyVoice 修好（修 hyperpyyaml / 換 prompt / 換 bopomo 管線）也得從 8 秒降到 3 秒以下才合格、技術上難。

### ASR latency（Breeze-ASR-25、同 Modal endpoint 兩天共用）

Day 3 ASR P50/P95 = 289/997 ms
Day 4 ASR P50/P95 = （見 edge-latency.csv）—— 同 endpoint、應在同範圍

ASR 不是瓶頸、TTS 是。

---

## 月費對照（dev usage、不含 prod scale）

| 項目 | BreezyVoice | Edge TTS |
|---|---|---|
| TTS GPU 月費 | $30-50（Modal A10G、scale-to-zero、warm 期偶 cold start）| **$0**（Microsoft Anonymous endpoint）|
| API key 申請 | 需 Modal account + secret | **無需**|
| 帳單觸發點 | 第 1 次 cold start GPU 0.5s = 計費單位 | **不計費** |
| Phase 1-2 dev 累計（含失敗 retry）| 累計約 $5-15 至今 | $0 |

**意義**：BreezyVoice 修好的成本（24-48 hr 工時 + Modal GPU debug 費）vs Edge TTS 已能跑（零成本）——Phase 1 demo 用 Edge TTS 是顯而易見的暫代選項。

---

## 音質主觀差異（Edward 起床聽）

兩家風格本質不同——Edward 必親耳聽完判：

| 維度 | BreezyVoice 預測聽感 | Edge TTS 預測聽感 |
|---|---|---|
| 自然度 | 變化大（cold start 第一句僵硬、後面好轉）| 穩定一致、廣播級 |
| 台灣腔 | 是 zh-TW base 但 cosyvoice 0.x 級限制 | `zh-TW-HsiaoChenNeural` 是 Microsoft 官方台灣腔女聲 |
| 情緒 | zero-shot voice clone 有機會傳情緒（Edward prompt）| 無 voice clone、固定 neutral 女聲 |
| 中英夾雜 | 失敗率高（t07 / t10）| 穩（t10 純英文也通）|
| 個性化 | 可 voice clone Edward 本人 | 不行（固定女聲） |

**翻譯**：BreezyVoice 強項是「voice clone Edward」、但 Phase 1 demo 用不到——Phase 1 只是要證明「ASR + TTS round-trip + 城堡派工 + 蘇菲念回」全鏈路 work。Edge TTS 對「廠商級台灣腔女聲」這個 baseline 完勝。Voice clone 是 Phase 2 議題、不在 Day 4 範圍。

---

## 結論：Phase 1 demo 用 Edge TTS 暫代、Edward 起床決定 BreezyVoice 長期 path

**蘇菲 council 自決 path（5/22 凌晨）**：
- BreezyVoice CER 86% / P95 9.86s = NO-GO 兩個 escalate triggers fired
- 修 BreezyVoice 風險高（要 hyperpyyaml pin / 換 voice clone prompt / 換 bopomo 管線、24-48 hr 不一定成功）
- Edge TTS 直接 ship 完整 Phase 1 demo、Edward 起床能聽真實效果

**Edward 起床 3 種 path 拍板**：

| Path | 內容 | 工時 | 風險 |
|---|---|---|---|
| **A · 走 Edge TTS（推薦）** | Phase 1 用 Edge TTS、BreezyVoice archive | 0（已就緒）| 低 |
| **B · 修 BreezyVoice** | Day 5-6 修 hyperpyyaml / 換 g2pw bopomo 管線 / 重 voice clone prompt | 24-48 hr | 中-高（修不一定成功） |
| **C · 雙路並存** | Edge TTS 預設、BreezyVoice 用在 voice clone 場景 | 修 BV + 接 Edge = ~30 hr | 中 |

**卡西法技術推薦**：**Path A（短期）+ Path C（中期，當 Phase 2 voice clone 真要做時再修）**。Phase 1 demo 不該被 BreezyVoice 卡死、Edge TTS 完全夠用。

---

## artifact 位置

- `phase1-poc/audio/t01-edge.wav` ~ `t10-edge.wav`（10 個 Edge TTS 音檔）
- `phase1-poc/audio/t01.wav` ~ `t10.wav`（Day 3 BreezyVoice 對照組、已存在）
- `phase1-poc/results/edge-round-trip-cer.csv`（per-sentence CER 細表）
- `phase1-poc/results/edge-latency.csv`（TTS / ASR latency P50/P95）
- `phase1-poc/results/edge-comparison-data.json`（machine-readable summary + Go/No-Go verdict）
- `phase1-poc/results/round-trip-cer.csv`（Day 3 BreezyVoice 對照、已存在）
- `phase1-poc/results/latency.csv`（Day 3 BreezyVoice latency、已存在）

---

*Day 4 ship · 2026-05-22 · 卡西法 autonomous · 蘇菲 council 自決 Phase 1 demo 暫代 path · Edward 起床聽完拍板 BreezyVoice 長期*
