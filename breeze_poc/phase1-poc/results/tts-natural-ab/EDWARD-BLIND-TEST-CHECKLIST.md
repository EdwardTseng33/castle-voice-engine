# Edward TTS 自然度 A/B 盲測 Checklist v2

**ship date**: 2026-05-22 v2（v1 同日 ship、v2 補 VibeVoice 蘇菲女聲版）
**branch**: voice-path/v2.0-breeze-poc · **owner**: 卡西法

> Edward 5/22 拍板：「不要客家、不要強求台灣腔、主軸自然度 + 人類感、可以測試一下」
> v1 城堡照辦——4 家 TTS、各 10 句、隨機盲聽、聽完打分
> v2 補：**VibeVoice 用真實女聲（Edge TTS 曉雨）當 voice clone 參考重跑 10 句**——回答 v1 留下的「VibeVoice 用合成噪音當 prompt 不公平」問題

## v2 新增焦點

| 對比軸 | v1 VibeVoice 版 | v2 VibeVoice-Sophie 版 |
|---|---|---|
| voice prompt | 合成 envelope-modulated noise | **Edge TTS 曉雨 30 秒蘇菲式 sample** |
| 預期效果 | 隨機女聲 / 不像特助 | 像 Edge TTS 曉雨 + VibeVoice 自然抑揚 |
| 答的問題 | VibeVoice 架構能不能跑 | **VibeVoice 能不能 voice clone 出蘇菲女聲** |

## 跑完 status（v2 新增）

| 家 | 成功 | P50 延遲 | 備註 |
|---|---|---|---|
| VibeVoice | 10/10 | 7.8s | v1 · 合成 noise prompt |
| **VibeVoice-Sophie**（v2）| **10/10** | **5.5s（含 1 cold start 19s）** | **v2 · Edge TTS 曉雨 voice clone 參考** |
| VoxCPM2 | 10/10 | 6.2s | v1 |
| Edge TTS | 10/10 | 556ms | v1 · zh-TW-HsiaoChenNeural 曉臻 baseline |
| BreezyVoice-fixed | 10/10 | 18.5s | v1 · clone Edward 男聲 |

**v2 Modal cost 估算**：A10G × ~70s inference + 1 cold start ≈ $0.10（遠低於 $5 cap）
**全部 wav 已 normalize 到 -1 dBFS peak**（Modal 端 build-in、實測 -0.92 dBFS 全 10 個一致）

---

## 30 秒看完版 v2

5 個資料夾、各 10 個音檔（編號 t01-t10）、對應同 1 組 10 句測試文本（sentences.txt）：

```
breeze_poc/phase1-poc/results/tts-natural-ab/
├── vibevoice/                      (v1 · 合成 noise prompt)
├── vibevoice-sophie-voice/         (v2 · Edge TTS 曉雨 voice clone) ⭐
├── voxcpm2/                        (v1 · OpenBMB VoxCPM2)
├── edge-tts/                       (v1 · Microsoft Edge TTS 曉臻女聲 baseline)
├── breezyvoice-fixed/              (v1 · MediaTek BreezyVoice clone Edward 男聲)
└── sophie-voice-prompts/           (v2 · voice clone 參考來源)
    └── edge-xiaoyu-sophie-prompt.mp3  (30 秒蘇菲式蘇菲口吻文本、曉雨 voice)
```

---

## v2 推薦聽法 · 兩階段

### 階段 1 · 聽參考來源
先聽 `sophie-voice-prompts/edge-xiaoyu-sophie-prompt.mp3`：
- 文本：「你好 Edward、我是蘇菲。今天先看一下你的工作清單、BeyondPath 那邊客戶的資料我整理好了、待會我跟你過一遍。等等休息一下、別累著、晚一點再說。」
- 音色：Edge TTS zh-TW-HsiaoYuNeural（曉雨、溫柔同理）
- 速率：-5%（比預設稍慢、像特助說話節奏）
- 這是 VibeVoice 學的「目標蘇菲聲」

### 階段 2 · A/B 對比 VibeVoice-Sophie vs Edge TTS 曉雨原版

對同一句（如 t05），3 邊聽：

| 維度 | Edge TTS 曉雨原版 | VibeVoice-Sophie | v1 VibeVoice |
|---|---|---|---|
| 音色像不像曉雨 | ⭐ 100% baseline | 聽聽看 voice clone 抓到幾成 | 不像（隨機 prompt） |
| 自然抑揚頓挫 | Azure neural · 還行但機械 | VibeVoice 強項 | 同 v1 |
| 情緒表達（t09/t10）| Edge 通常平 | VibeVoice 應該更鮮活 | 同 v1 |
| 中英混講（t07/t08）| Edge 穩定 | 看 VibeVoice 在 voice clone 下能否穩 | 同 v1 |

**核心對比**：「Edge TTS 已經很穩、VibeVoice 加 voice clone 後值不值得多付 7s 延遲」

---

## v2 評分加題

對 VibeVoice-Sophie 額外打 1 分：

**E. Voice clone 像不像（vs 曉雨原版）** 1-5：
- 5 = 聽不出來是 clone、跟原版一樣
- 4 = 大致像、細節有些不同
- 3 = 抓到女聲特徵但音色明顯有變
- 2 = 聽得出是另一個女聲、只有大方向像
- 1 = clone 失敗 / 完全不像

---

## v2 評分表（請填）

| 家 | A 自然 | B 情緒 | C 工作 | D 穩定 | E Clone | 平均 | 直覺評語 |
|---|---|---|---|---|---|---|---|
| VibeVoice（v1 noise）| _ | _ | _ | _ | N/A | _ | |
| **VibeVoice-Sophie（v2）** ⭐ | _ | _ | _ | _ | _ | _ | |
| VoxCPM2 | _ | _ | _ | _ | N/A | _ | |
| Edge TTS 曉臻 | _ | _ | _ | _ | N/A | _ | |
| Edge TTS 曉雨（參考） | _ | _ | _ | _ | N/A | _ | |
| BreezyVoice-fixed | _ | _ | _ | _ | _ | _ | |

**第 1 名（蘇菲女聲主路用哪家）**：______
**為什麼**：______

---

## v2 下一步決策樹（Phase 2 主路）

**若 VibeVoice-Sophie ≥ 4.0 平均、Clone ≥ 4 分**
→ 進 Phase 2 用 VibeVoice + Edge TTS 曉雨 voice prompt 當蘇菲主聲、長度延遲可接受（5-8s）

**若 Edge TTS 曉雨 ≥ 4.0、VibeVoice-Sophie < 4.0**
→ Phase 2 直接用 Edge TTS 曉雨當蘇菲主聲（556ms 延遲秒殺）、之後找其他 model 突破自然度

**若兩家都 < 4.0**
→ Phase 2 考慮 ElevenLabs / OpenAI TTS-1-HD（付費 API、跨 PoC 預算討論）

---

## v2 技術細節

### 為什麼選曉雨當 voice prompt 源？
1. 曉雨（HsiaoYuNeural）= zh-TW Azure neural voice、溫柔同理 tone、最接近「蘇菲特助女聲」人設
2. Edge TTS 免費 / 不離境 / Azure ToS 合規
3. 30 秒長度 = VibeVoice voice clone reference 推薦上限（夠 capture 音色、不會 overfit）
4. -5% rate = 比預設稍慢、像特助說話節奏

### VibeVoice voice clone 工作原理
- 不是 fine-tune model 本身
- 推 inference 時把 voice sample 當 in-context prompt
- model 自動 capture 音色 + prosody pattern 套到目標 text
- 跟 fine-tune 比：零訓練成本、即時切換、但音色相似度通常 70-90% 不到 100%

### Modal endpoint
- **新 app**：`vibevoice-sophie`（5/22 14:00 deploy）
- **舊 app**：`vibevoice-poc`（v1 · 仍 live、可隨時 retry）
- **call 方式**：Modal class direct call（不走 HTTP endpoint、省 cold start）

---

## v1 段落保留 reminder

下面 v1 內容（4 家對比表 / 評分 rubric / 10 句測試文本 / 各家備註）**仍適用**、v2 只是補新一家。

---

## 4 家對比表 v1（保留）

| 軸 | VibeVoice | VoxCPM2 | Edge TTS | BreezyVoice-fixed |
|---|---|---|---|---|
| **模型** | microsoft/VibeVoice-1.5B | openbmb/VoxCPM2 | Azure Neural | MediaTek-Research/BreezyVoice |
| **聲音** | 預設 demo speaker | 預設女聲 | zh-TW-HsiaoChenNeural（曉臻女聲） | clone Edward 男聲 |
| **voice clone** | 內建 speaker · 可 zero-shot | zero-shot 支援 | 不支援 | zero-shot |
| **授權** | MIT | Apache-2.0 | Edge TTS terms | Apache-2.0 |
| **隱私** | self-host（Modal） | self-host（Modal） | 走 Azure cloud | self-host（Modal） |
| **月費** | 約 $5-15 GPU | 約 $5-15 GPU | 免費 | 約 $5-15 GPU |
| **延遲 P50** | 7.8s | 6.2s | 556ms | 18.5s |

---

## 10 句測試文本（4 軸覆蓋）

**A 聊天日常**：
- t01: 今天天氣不錯、想出去走走嗎？
- t02: 等等吃飯有想吃什麼？
- t03: 最近忙翻了、好想休息一下。

**B 工作交付**：
- t04: 派蕪菁頭看 BeyondPath 今天的數據、跌幅超過 30% 就提醒我。
- t05: 明天會議我們要討論 v2.0 的計畫、特別是第三階段的鏡頭功能。
- t06: 客戶那邊的提案、麻煩你幫我整理一份完整版給我。

**C 中英混講**：
- t07: 我要把 PR 上傳到 main 之前先跑 lint。
- t08: BeyondPath 那個 dashboard 的 retention 數據看起來不太對。

**D 情緒語氣**：
- t09:（興奮）太好了！這次客戶真的簽約了！
- t10:（疲累）今天先到這、明天再說、我先休息一下。

---

## 評分 rubric v1（保留 · A/B/C/D 給所有家用、E 給 voice clone 家 v2 新增）

**A. 自然度（人類感）** 1-5
**B. 情緒表達（t09/t10）** 1-5
**C. 工作場景適配（t04-t08）** 1-5
**D. 長對話穩定（10 句連聽）** 1-5
**E. Voice clone 像不像（vs 曉雨參考）** 1-5 ⭐ v2 新增、僅 VibeVoice-Sophie / BreezyVoice 適用

---

## 檔案位置 reminder v2

- v2 蘇菲女聲：`breeze_poc/phase1-poc/results/tts-natural-ab/vibevoice-sophie-voice/t01-t10.wav`
- v2 voice prompt 來源：`breeze_poc/phase1-poc/results/tts-natural-ab/sophie-voice-prompts/edge-xiaoyu-sophie-prompt.mp3`
- v1 4 家：`vibevoice/` / `voxcpm2/` / `edge-tts/` / `breezyvoice-fixed/`
- 各家 metadata：`<家>/metadata.json`
- 本檔：`EDWARD-BLIND-TEST-CHECKLIST.md`（v2）

shipping branch：`voice-path/v2.0-breeze-poc`（castle/main 零污染）

---

## 卡西法 v2 心得

- v1 VibeVoice 沒給真實 voice prompt 是不公平、v2 補完才看得出 VibeVoice 真正實力
- 曉雨 voice 出來的 prompt 比想像中蘇菲——溫柔但不黏膩、剛好的同理感
- VibeVoice voice clone 工作得很穩、10/10 PASS、無 retry
- 延遲 5.5s P50（含 1 cold start 19s）比 v1 的 7.8s P50 還快（架構複用、模型沒換）
- 跟 Edge TTS 曉雨原版（556ms）比慢 10 倍——值不值得 = Edward 聽完 verdict
- 若選 VibeVoice-Sophie：未來可換 prompt voice（換到 Voice Path 真特助 voice）就是換 voice profile、不必重 train
- 若選 Edge TTS 曉雨：直接用、零 inference cost、但無法換音色（綁 Azure 預訓 voice 池）

**📞 任何疑問** → 蘇菲（主對話）或卡西法（subagent）
