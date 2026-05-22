# Edward TTS 自然度 A/B 盲測 Checklist

**ship date**: 2026-05-22 · **branch**: voice-path/v2.0-breeze-poc · **owner**: 卡西法

> Edward 5/22 拍板：「不要客家、不要強求台灣腔、主軸自然度 + 人類感、可以測試一下」
> 城堡照辦——跑了 4 家 TTS、各家 10 句、隨機盲聽、聽完打分。

## 跑完 status（截至 ship 時間）

| 家 | 成功 | P50 延遲 | 備註 |
|---|---|---|---|
| VibeVoice | 10/10 | 7.8s | 4 句首次跑撞 cold-start 500、retry 全過 |
| VoxCPM2 | 10/10 | 6.2s | 第 1 句 cold start 8 min、後面穩定 5-7s |
| Edge TTS | 10/10 | 556ms | 永遠的快、永遠的穩、輸出 mp3（其他家輸出 wav） |
| BreezyVoice-fixed | 10/10 | 18.5s（含 cold start）| 修對入口後可聽 · 穩定 inference 12s |

**總 audio 數量：40 個（4 家 × 10 句）**
**總 Modal cost 估算：< $5（僅占任務 budget $10 一半）**


---

## 30 秒看完版

4 個資料夾、各 10 個音檔（編號 t01-t10）、對應同 1 組 10 句測試文本（sentences.txt）：

```
breeze_poc/phase1-poc/results/tts-natural-ab/
├── vibevoice/         (Microsoft VibeVoice-1.5B)
├── voxcpm2/           (OpenBMB VoxCPM2)
├── edge-tts/          (Microsoft Edge TTS · zh-TW-HsiaoChenNeural · baseline)
└── breezyvoice-fixed/ (MediaTek BreezyVoice · entry 修對版)
```

**推薦聽法**：
1. 隨機抽 t01-t10 一個編號（例 t05）
2. 用 Windows Media Player / VLC 同時打開 4 個資料夾的同編號
3. 不看資料夾名、用 4 鍵盤 hotkey 切換（哪家不告訴自己）
4. 4 個都聽完才看資料夾名揭曉是哪家
5. 換下一句重複

---

## 4 家對比表

| 軸 | VibeVoice | VoxCPM2 | Edge TTS | BreezyVoice-fixed |
|---|---|---|---|---|
| **模型** | microsoft/VibeVoice-1.5B | openbmb/VoxCPM2 | Azure Neural | MediaTek-Research/BreezyVoice |
| **聲音** | 預設 demo speaker | 預設女聲 | zh-TW-HsiaoChenNeural（曉臻女聲） | clone Edward 男聲 |
| **voice clone** | 內建 speaker · 可 zero-shot | zero-shot 支援 | 不支援（neural voice 固定） | zero-shot（本次 clone Edward）|
| **授權** | MIT | Apache-2.0 | Edge TTS terms / Azure ToS | Apache-2.0 |
| **隱私** | self-host（Modal） | self-host（Modal） | 走 Azure cloud（資料離境） | self-host（Modal） |
| **月費** | 約 $5-15/月 GPU spend | 約 $5-15/月 GPU spend | 免費（含 rate limit） | 約 $5-15/月 GPU spend |
| **延遲 P50** | 7.8s（含 cold start） | 6.2s（含 cold start） | 556ms | 18.5s（含 cold start） |
| **延遲 P95** | 26.3s | 473s（含第 1 句 cold start 8 min） | 1.3s | 105s（含第 1 句 cold start） |
| **本次配置** | Modal A10G | Modal A10G | edge-tts python lib | Modal A10G + g2pw 注音 prefix |

---

## 評分 rubric（每家總分 = 4 軸平均、滿分 5 分）

**A. 自然度（人類感）** 1-5：
- 5 = 像真人講話、抑揚頓挫自然、聽不出機器味
- 4 = 大致自然、偶爾感覺到機器
- 3 = 中性、聽得出 TTS 但不刺耳
- 2 = 明顯機器味、有停頓不對勁
- 1 = 嚴重機器口音 / 失真 / 切音不對

**B. 情緒表達（t09/t10 場景）** 1-5：
- t09 興奮句「太好了！這次客戶真的簽約了！」
- t10 疲累句「今天先到這、明天再說、我先休息一下。」
- 5 = 情緒到位、聽得出來
- 3 = 中性平淡
- 1 = 完全沒情緒

**C. 工作場景適配（t04-t08）** 1-5：
- 中英混講不彆扭（BeyondPath / lint / PR / retention 等英文詞）
- 名詞清楚（蕪菁頭、v2.0、第三階段）
- 5 = 自然流暢、英文唸對
- 1 = 英文唸不出 / 切音斷裂

**D. 長對話穩定（10 句連聽）** 1-5：
- 聲音前後一致（不會 t01 跟 t10 像兩個人）
- 音量穩定（不會某句特別大聲 / 小聲）
- 5 = 完全穩定
- 1 = 起伏太大不能聽

---

## 評分表（請填）

| 家 | A 自然度 | B 情緒 | C 工作場景 | D 長對話穩定 | 平均 | 直覺評語 |
|---|---|---|---|---|---|---|
| VibeVoice | _ | _ | _ | _ | _ | |
| VoxCPM2 | _ | _ | _ | _ | _ | |
| Edge TTS | _ | _ | _ | _ | _ | |
| BreezyVoice-fixed | _ | _ | _ | _ | _ | |

**第 1 名**：______
**為什麼**：______

**不選的**：______
**為什麼**：______

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

## 為什麼 BreezyVoice 跟其他三家不同

BreezyVoice 是 **zero-shot voice clone** 模型（同 CosyVoice 家族）、必須給「prompt 音檔」當參考聲。本次用 `edward_8s_prompt.wav`（Edward 自己錄的 8 秒）→ 所以你會聽到 **Edward 自己男聲讀那 10 句**。

這跟「VibeVoice / VoxCPM2 / Edge」聽到的「預設女聲」**不是同 voice profile**。

評分時請聚焦：
- BreezyVoice = clone 像不像、Edward 的 voice character 有沒有抓到、繁中發音準不準
- 其他三家 = 預設女聲本身的「自然度 + 人類感」

**若 Edward 偏好「我自己 voice 上線」** → BreezyVoice 軸更重要
**若 Edward 偏好「另一個女聲特助 voice」** → VibeVoice / VoxCPM2 / Edge 軸更重要

---


## VibeVoice 注意事項（重要）

VibeVoice 是 Microsoft 為「multi-speaker 長 podcast 生成」設計的、不是針對單句 TTS。本次測試發現：

- **輸出時長不穩**：10 個字的句子可能生成 4 秒或 24 秒（model 自由發揮）
- **voice sample 必要**：必須給 prompt voice、本次用 synthetic envelope-modulated noise（無真實 prompt）→ 音色「不自然」是預期內
- **若選 VibeVoice 作主力** → 必須準備 Edward 真實 voice prompt 重跑、否則只能聽 architecture sanity
- **更合理的 use case**：對話腳本（Speaker 0: ... Speaker 1: ...）podcast 風格、不是「秘書幫你唸 1 句」

---

## Day 3 走錯入口、Day 4 已修

BreezyVoice Day 3 用 `inference_zero_shot`（會跑 WeTextProcessing normalize 把繁中聲調丟掉）→ 自然度爛。

Day 4 修對：
1. 改用 `inference_zero_shot_no_normalize`（保聲調 + 句讀）
2. 加 g2pw 把中文 → 注音 prefix（BreezyVoice 官方推薦繁中走法）
3. prompt voice = `edward_8s_prompt.wav`

結果：10/10 成功、P50 ~18s 含 cold start、穩定後 inference ~12s。

---

## 下一步（Edward 決定）

1. **告訴蘇菲哪家第 1 名 + 為什麼** → 進 Phase 1.5 deep dive 該家（更多 voice profile + 情緒參數 + streaming）
2. **若 4 家都不夠自然** → Phase 2 考慮 ElevenLabs / OpenAI TTS-1-HD / Google Cloud TTS（付費 API、不在這 PoC 範圍）
3. **若選 Edge TTS** → 直接 lock baseline、進 Voice Path Phase 2 對話 loop
4. **若選 BreezyVoice + Edward voice clone** → 進「我自己的 AI 聲音」方向、配 Phase 4 商用 sulima sign-off 流程

---

## 檔案位置 reminder

- 音檔：`breeze_poc/phase1-poc/results/tts-natural-ab/<家>/t01-t10.wav`（Edge 為 .mp3）
- 各家 metadata：`<家>/metadata.json`（含 latency / 模型版本 / license / endpoint）
- 測試文本：`sentences.txt`
- 本檔：`EDWARD-BLIND-TEST-CHECKLIST.md`

shipping branch：`voice-path/v2.0-breeze-poc`（castle/main 零污染）

---

**📞 任何疑問** → 蘇菲（主對話）或卡西法（subagent）。
**🔥 卡西法心得** → BreezyVoice 修對入口後其實很能聽（穩定 inference 12s）、但對「即時對話」太慢。Edge TTS 永遠的 500ms baseline。VibeVoice + VoxCPM2 你聽聽看就知道值不值得這 Modal 開銷。
