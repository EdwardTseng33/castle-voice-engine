# Voice Path v2.0 Phase 1 PoC · Breeze Stack 並存試做

> Branch: `voice-path/v2.0-breeze-poc` (隔離、不污染 castle/main)
> 時程: 5-10 天 · Mid-progress @ Day 3 · Final demo @ Day 7-10
> Owner: 卡西法 · Reviewer: 主對話蘇菲 → Edward
> Gate 5: sulima 5 條件全綠

## 目標

不拆 OpenAI Realtime backend (`app.py`)、新增第二條 Breeze stack 路徑
(`app_breeze.py`) 作對照組。Phase 1 PoC 結束後 Edward 決定:

- A. 採用 Breeze 全替換 → v2.1 拆 OpenAI
- B. 維持 OpenAI、Breeze 失敗 → PoC archive
- C. 並存策略 (Breeze 中文 / OpenAI 英文 fallback) → v2.1 dual-backend

## Stack 對照

| 元件 | OpenAI Realtime (現役) | Breeze (PoC) |
|---|---|---|
| ASR | Whisper-1 via Realtime | Breeze-ASR-25 (Apache 2.0) |
| LLM | GPT-4o Realtime | Llama-Breeze2 (Llama 3.2 CL) |
| TTS | Realtime audio | BreezyVoice (Apache 2.0, 內建台灣腔女聲) |
| 聲紋認證 | 無 | Picovoice Eagle (商用授權 PoC 用個人版) |
| Modal GPU | CPU only (ephemeral token mint) | A10G (本地 inference) |
| 月費 | ~$0.06+$0.24/min (用量計費) | A10G ~$0.001/sec · scale-to-zero |

## 5 條件 (Gate 5 必過)

| # | Condition | 實作對應 |
|---|---|---|
| 1 | 聲音樣本 never 寫 Modal Volume | `app_breeze.py` 用 function input bytes / `tempfile` 處理 / 函式結束自動 GC |
| 2 | PoC 結束 7 天內 Edward 跑 cleanup 確認零殘留 | `cleanup_modal_volume.py` + README 1 行教學 |
| 3 | Modal account 2FA | Edward 自證 (本任務外、提醒在 Final report) |
| 4 | Modal CLI token < 90 天 rotate | ✅ `.modal.toml` 創於 2026-04-28 = 24 天 < 90 天 |
| 5 | PoC 不接外部使用者 / 不收客戶聲音 | 端點僅 Edward 個人 API key 限定、`/breeze/*` 路由有 auth check |

## 隱私架構鐵律 (build 時必守)

- 聲音檔 **never** `volume.persist()` / `volume.commit()`
- 用 `tempfile.NamedTemporaryFile` (auto cleanup) / 直接 bytes in memory
- function teardown 前 explicit `os.remove()` + log "audio purged"
- Phase 3 webcam 在本 PoC 完全不碰、留 Phase 3 sulima 再評

## 量測指標 (Final demo 要交)

1. **Breeze-ASR-25 中文聽錯率**: 10 句 Edward 樣本實測 vs 廠商宣稱 7.97%
2. **BreezyVoice 生成延遲**: per-句 ms (首句 cold start vs warm)
3. **Modal A10G VRAM 佔用**: peak GB
4. **Modal A10G 月費估算**: 假設 Edward 每日用 30 min · scale-to-zero
5. **Eagle 聲紋誤拒率**: Edward 聲音 ✅ / 他人聲音 (請主對話蘇菲幫忙找對照樣本) ❌
6. **Function calling 派 subagent 成功率**: 5 testcase 成功 N/5

## Day-by-day

| Day | Deliverable |
|---|---|
| 1 (今) | PoC branch 開 · PLAN.md · `app_breeze.py` skeleton (ffmpeg + 空函式) · `register_eagle_speaker.py` (Eagle 註冊 stub) · 上傳 m4a 轉 WAV 跑通 |
| 2 | `app_breeze.py` 接 Breeze-ASR-25 (HuggingFace download in Modal image build) · 10 句樣本 ASR 跑通 |
| 3 | **MID-PROGRESS 報告** · BreezyVoice TTS 接上 · 生成 1 段中文音檔 · 延遲量測初值 · 任何 NO-GO 信號 |
| 4 | Llama-Breeze2 接上 · Sophie persona prompt 跑通 (沿用 sophie.yaml) |
| 5 | Picovoice Eagle 聲紋註冊 + 認證測試 |
| 6 | Claude function calling 接 1 個 subagent (蕪菁頭 BeyondPath retention) demo |
| 7-8 | E2E demo 整合 · 量測表格收完 · `cleanup_modal_volume.py` 寫完 + 測過 |
| 9-10 | Final report + verdict (採 A/B/C) + 給主對話蘇菲整合 |

## NO-GO escalate 觸發

- Breeze-ASR-25 中文聽錯率 > 15% (廠商宣稱 7.97% 的 2x)
- BreezyVoice 延遲 > 3 sec / 句 (對話體驗破)
- Modal A10G 月費估算 > $200 (Edward 預算護欄)
- License 任一條失效 / sulima reviewed 結果改變

任一觸發 → 立即 escalate 主對話蘇菲、不硬撐。

## 不在範圍

- ❌ Phase 2 voice clone (Edward 拍板暫不做)
- ❌ Phase 3 webcam (sulima 未開 Gate)
- ❌ 動現役 `app.py` (並存策略、零 regression)
- ❌ Production launch (PoC only)
