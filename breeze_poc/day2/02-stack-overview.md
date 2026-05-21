# Breeze Stack 各 component 入門卡（Day 2-6）

## 1. Breeze-ASR-25（Day 2-3）

- **任務**：中文 + 中英 code-switch ASR
- **基底**：Whisper-large-v3 fine-tune
- **HF**：`MediaTek-Research/Breeze-ASR-25`
- **GPU**：A10G 24GB（fp16 ~3GB weight）
- **延遲預估**：30s segment ~ 1-2s（A10G fp16）
- **License**：Apache-2.0

## 2. BreezyVoice TTS（Day 3-4）

- **任務**：中文 TTS、預設台灣腔女聲
- **基底**：CosyVoice 系列（MediaTek 二訓）
- **HF**：`MediaTek-Research/BreezyVoice`（待 Day 3 confirm 確切 ID）
- **GPU**：A10G 24GB（fp16）
- **延遲預估**：1 段 ~ 500ms-1s streaming
- **License**：Apache-2.0
- **客製音色**：v2 PoC 不做（Edward 拍板）、預設台灣腔女聲就好

## 3. Picovoice Eagle（Day 5-6）

- **任務**：聲紋辨識（個人化、防陌生人）
- **SDK**：`pveagle` Python（commercial、PoC 用個人版 KEY）
- **註冊**：≥ 25s 聲音樣本（edward_for_eagle.m4a 1.56MB ~60-90s OK）
- **驗證**：每次語音輸入前跑 ~50ms
- **License**：個人非商用、PoC OK；商用要購授權（Phase 2 評估）
- **隱私**：聲紋 embedding 存 Modal Volume？→ Gate 5 條件 1 衝突
  - **解**：聲紋 embedding 不存 Volume、store 在 Modal Secret OR `~/.modal` Edward 個人機器、不放雲端
  - **Day 5 設計時再 council 確認**

## 4. Llama-Breeze2（Day 7-8）

- **任務**：中文對話 + 城堡 7 subagent function calling
- **基底**：Llama-3-8B fine-tune（MediaTek）
- **HF**：`MediaTek-Research/Llama-3-Breeze-Instruct`（待 confirm）
- **GPU**：A10G 8GB（fp16 8B model ~ 16GB、需要 quant 或 A100）
  - **撞點**：A10G 24GB 同時 load Breeze-ASR-25（3GB）+ BreezyVoice（??GB）+ Llama-Breeze2（16GB）= 可能爆 VRAM
  - **escalate 觸發**：Phase 2 PoC Day 7-8 若撞、要重新規劃 model 切換 / 分 function（ASR/TTS 一個 function、LLM 另一個 function）
- **alternative**：Day 7-8 LLM 還是用 Claude API（city function calling）= **目前主路徑**、Llama-Breeze2 待 v2.1 評估
- **Edward 5/22 拍板要 Claude function calling 接城堡 subagent** ← 跟原本 Day 7-8 對齊

## 5. Whisper API（控制組對照）

- 廠商產品中文 ASR baseline 7.97%
- Day 2-3 同 10 句 Breeze-ASR-25 跑 + 同 10 句 OpenAI whisper-large-v3 跑 → 雙軌對比
- 公平基準

## A10G VRAM 預算（critical）

| Stage | Model 同時 load | VRAM 預估 | 24GB 剩 |
|---|---|---|---|
| Day 2-3 | Breeze-ASR-25 only | 3 GB | 21 GB |
| Day 3-4 | + BreezyVoice | 3 + 2-4 GB | 17-19 GB |
| Day 5-6 | + Eagle（CPU、不用 GPU） | 5-7 GB | 17-19 GB |
| Day 7-8 | + Claude API（外部、不用 GPU） | 5-7 GB | 17-19 GB |

A10G 24GB 跑 Breeze 全 stack（不含 Llama）**裕度充足**。
若 Phase 2 要加 Llama-Breeze2 8B（16GB fp16）→ 撞 VRAM、必拆 function。

## Cost 預算（PoC 期）

| 項目 | Modal 計價 | PoC 10 天估 |
|---|---|---|
| A10G GPU active | $0.000164 / sec | 每天 active 1hr = $0.59 / 10 天 $5.9 |
| CPU function（preprocess） | $0.000022 / sec | 忽略 |
| Volume storage | $0.20 / GB-month | 不用 Volume = $0 |
| Egress | $0.10 / GB | < 1GB = 忽略 |

**估**：PoC 10 天 < $10 USD = 遠低於 escalate 觸發 $50 上限 ✅

實際每日跑完後我會記錄 Modal `usage report` 進 Day N progress note、不憑感覺估。
