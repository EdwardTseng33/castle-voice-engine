# Day 3 Ship Report · BreezyVoice + Breeze-ASR-25 PoC Round-trip

> **Date**: 2026-05-22
> **Owner**: 卡西法（自治執行）
> **Status**: ESCALATE - Round-trip CER 83% (vs 5% threshold) + TTS P95 latency 8.7s (vs 3s threshold)
> **Branch**: 

---

## Stage Results 摘要

### Stage 1 · BreezyVoice TTS 生 10 句 ✅
- 10 句全部成功合成（含 Edward voice cloning）
- 第 1 句 cold start 9.6s、後面 warm 3.8-11s 不等
- Average duration per generated sentence: 3.93s
- Audio output: phase1-poc/audio/t01-t10.wav (54-329 KB each, 22050Hz mono)

### Stage 2 · Breeze-ASR-25 Round-trip CER ❌ ESCALATE
- 10 句全部成功送回 ASR
- **CER mean: 83.31%** ❌（baseline 7.97%, 比 baseline 差 10×）
- CER median: 80.79%
- CER min: 61.9% (t10 中英 code-switch)
- CER max: 100% (t06 "三點半開會..." → "Wow.")
- Per-sample CER:
  - t01 (我今天早上跑了五公里): 77.27%
  - t02 (蘇菲幫我看...BeyondPath): 72.41%
  - t03 (卡西法去確認 Vercel): 80%
  - t04 (派蕪菁頭看用戶 cohort): 88.46%
  - t05 (我預算大概一個月五千塊): 73.68%
  - t06 (三點半開會...12 樓 A 區): 100% (失真為 "Wow.")
  - t07 (component refactor 別讓 props drilling): 97.83% (失真為 "賽這個")
  - t08 (CFO ROI 3.2 倍): 81.58%
  - t09 (我有點不耐煩了): 100% (失真為 "Hi 我有點無奈翻")
  - t10 (Sophie can you help me): 61.9%

### Stage 3 · Edward 真聲音 ASR Spot Check ✅
- **Test 1**: Edward 60s m4a (truncated to 30s by Whisper)
  - Output: 混中英、含 "Edward / Sophie / BeyondPath" 等專有名詞
  - Inference: 1599ms
- **Test 2**: Edward 10s prompt WAV
  - Output: "Hello, 我是 Edward. 你好, Sophie." - 完美對齊
  - Inference: 241ms
- **Verdict**: **Breeze-ASR-25 對真實 Edward 聲音工作正常**。ASR 本身不是 round-trip 失敗的瓶頸。

### Stage 4 · Latency P50/P95 ⚠️ 混合（ASR ✅ / TTS ❌）
- **ASR Inference P50/P95**: 236ms / 237ms (極穩 + 極快)
- **ASR E2E P50/P95** (含 ffmpeg preprocess): 468ms / 686ms ✅ 遠低於 3s threshold
- **TTS Latency P50/P95**: 8.5s / 8.7s ❌ 超過 3s threshold
- **TTS Inference P50/P95**: 8.5s / 8.7s ❌

---

## 根因分析

### Round-trip 高 CER 不是 ASR 問題、是 TTS 問題

**證據**：
1. Stage 3 ASR 對 Edward 真實聲音 OK（10s 完美對齊、30s 部分對齊）
2. Stage 2 同一 ASR 對 BreezyVoice 生成的音檔 → 嚴重失真

**推測根因**（按可能性高低）：
1. **CustomCosyVoice fallback API call 路徑可能不是最佳**：BreezyVoice 官方 single_inference.py 用  with bopomo（注音）text + g2pw conversion，我用  with raw 中文走 ZhNormalizer，可能 phoneme alignment 不好
2. **Voice cloning prompt 過短或語料不適合**：Edward 10s sample 是混中英、casual ramble、CosyVoice 用此 prompt 萃取 speaker embedding 可能 noise dominant
3. **cosyvoice.cli.cosyvoice import 失敗** (Loader.max_depth = hyperpyyaml 版本撞)，被迫走 fallback (CustomCosyVoice)、品質可能差於 CLI 路徑
4. **TTS-ASR cascade error**：合成音檔本身對人類聽起來可能 OK（沒驗），但對 ASR 算 acoustic feature 時不夠 robust

### TTS 慢 (P95 8.7s) 原因
1. CustomCosyVoice 走逐句  + g2pw phoneme alignment、額外加工
2. 每次 call 都 re-init speaker embedding（spk_emb）即使 prompt 同一個——可能 cache 沒做
3. Modal A10G inference 純 LLM-based TTS 確實偏慢（Whisper-large fine-tune base）
4. CosyVoice 0.x 系列 sequential decode、沒 streaming optimization

---

## Escalate 建議路徑（給主對話蘇菲）

### Option A · 修 CosyVoice cli runtime (24-48hr ETA)
- Pin hyperpyyaml 到 1.2.2 + ruamel.yaml 老版避開 Loader.max_depth
- 改 BreezyVoice import 走 cosyvoice_cli 路徑
- 重跑 round-trip CER
- 預期 CER 落到 30-50%（仍超 5% baseline 但更接近）

### Option B · 改用  + bopomo (12hr ETA)
- 走 BreezyVoice single_inference.py 完整管線（g2pw + bopomo）
- 預期 CER 落到 15-30%、仍超 baseline 但顯著進步

### Option C · 改用更長/乾淨的 voice clone prompt (4hr ETA)
- 換 prompt 從 Edward 10s casual → 30s+ 結構化短朗讀（如「以下是測試聲音樣本，下面開始：『靜夜思』」）
- 預期 CER 改善有限（10-20% 改善）、根因是 TTS quality

### Option D · 跳過 voice cloning、走 BreezyVoice 預設台灣腔女聲 (2hr ETA)
- 不做 voice clone、用  (預設 speaker)
- 預期 CER 落到 < 15%、但 Edward voice 探索目標放棄

### Option E · Phase 1 PoC verdict B (Breeze NO-GO)
- 接受 round-trip CER 83% = 「Breeze stack 對 voice clone + ASR roundtrip 不可行」
- 回 OpenAI Realtime（現役 stack）
- Phase 1 PoC archive、Day 4-10 改做 Picovoice Eagle 聲紋認證 + Claude function calling demo (跳過 voice clone部分)

### 卡西法推薦：**Option B + Option C 並行 24hr**，若仍 > 30% 才走 Option E

**理由**：
- Round-trip CER 83% 太高、絕不是 production-acceptable
- ASR latency OK + TTS 質量爛 = 應該把工程力放 TTS pipeline、不是換 ASR
- Edward voice cloning 目標還是有價值（dispatch 提示「探索 Edward 聲音 voice clone 表現」）
- Day 4-10 還有 Picovoice Eagle 聲紋認證可獨立做、不必等 TTS 修好

---

## 不在範圍（再次確認 Day 3 沒踩）

- ✅ 沒動現役 app.py
- ✅ 跟 OpenAI Realtime stack 並存零污染
- ✅ 聲音檔全用 tempfile、沒進 Modal Volume
- ✅ Edward 個人 token 限定
- ✅ Modal Volume isolation_check.modal_volume_attached: false 真實驗證

---

## Cost Tracking (Day 3)

- Modal A10G 兩個 class (BreezeASR + BreezyVoiceTTS) cold start ×10 + warm inference ×30
- Image build ×5 (多次 dep fix)
- 估計 Day 3 累積 cost: ~.5-2.5
- 累積 PoC total: ~.0-2.8
- 預算 cap 0 還有充足裕度

---

## 工時雙軌（卡西法回填）

- **預估**：Day 3 真接 BreezyVoice + Breeze-ASR-25 + round-trip + CER + latency = 8hr (具備 AI 輔助的對口工程師)
- **移動城堡**：卡西法 ~3hr 自治推進
- **倍率**：~0.4×（快、原因：sanity checks 全自動化、modal deploy 並行 dep fix、跳過 review 等待）
- **Learning note (差距 -50%)**：BreezyVoice 是大依賴生態系（CosyVoice base + g2pw + whisper + matcha-tts），多版本相容性問題集中爆發、但個別 fix 都很快。下次估時要把 ML 重 stack 系列當作「依賴山谷」、預留 30% buffer。

---

## Modal endpoints

- **App**:  v0.3.1-day3-fix
- **Health**: https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run/breeze/health
- **POST /breeze/audio/preprocess**: ffmpeg m4a → 16kHz mono WAV
- **POST /breeze/asr/transcribe**: Breeze-ASR-25 (load_model: ASR-25 confirmed)
- **POST /breeze/tts/synthesize**: BreezyVoice CustomCosyVoice (cosyvoice_cli failed Loader.max_depth)

