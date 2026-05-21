# Day 3 Complete (Voice Path v2.0 Breeze PoC) · Preliminary

> calcifer self-driven ship 5/22 凌晨 · branch `voice-path/v2.0-breeze-poc`
> 本檔在跑完 day3_runner 後自動 overwrite；目前是 pre-run preliminary

---

## 真實當前狀態（5/22 03:30 TST）

| 項目 | 狀態 | 證據 |
|---|---|---|
| Modal app `castle-voice-engine-breeze-poc` deploy | ✅ live | `py -m modal app list` |
| /breeze/health | ✅ 200 OK | health JSON v0.3.0-day3 |
| /breeze/audio/preprocess（CPU ffmpeg） | ✅ 跑通 | edward m4a → 16kHz WAV pipeline 驗證 |
| /breeze/asr/transcribe（A10G GPU） | ✅ 跑通 | Edward voice 30s → 1.28s warm latency |
| /breeze/tts/synthesize（A10G GPU） | ⏳ image build 中（tn module fix） | 5/22 03:25 deploy in flight |

**核心發現**：
- Breeze-ASR-25 真實跑通、Edward 30 秒中文聲音 server latency **1.28 秒**（A10G fp16、warm）
- TTS 卡在 BreezyVoice runtime dependency（`tn` from WeTextProcessing missing）→ 已加進 image redeploy 中

---

## 4 escalate trigger 狀態（自治判斷）

| # | Trigger | 狀態 |
|---|---|---|
| 1 | Breeze ASR CER > 15% | ⏳ 等 TTS 上線、round-trip CER 跑 |
| 2 | BreezyVoice 延遲 > 3s/句 | ⏳ 待測 |
| 3 | A10G VRAM 撞 24GB | 🟢 ASR fp16 < 5GB、TTS 未測 |
| 4 | Modal 月費 > $50 | 🟢 < $1（5/22 凌晨多次 redeploy CPU + ASR cold start 1 次） |

**不 escalate** — image 修復 in progress、可控。

---

## Day 3 自治處理的 4 個 root cause（卡西法 lesson）

| # | 問題 | Root cause | Fix |
|---|---|---|---|
| 1 | BreezyVoice cold start crash `No module named 'tn'` | WeTextProcessing 漏裝（cosyvoice/cli/frontend.py 需 tn.chinese.normalizer） | 加 `WeTextProcessing==1.0.3`（對齊 BreezyVoice upstream） |
| 2 | `matcha-tts==0.0.5.1` vs `diffusers>=0.27` resolution fail | matcha-tts 0.0.5.1 pin diffusers==0.25.0、太舊 | 拿掉 matcha-tts pip dep、改用 BreezyVoice repo 的 `third_party/Matcha-TTS` submodule + git clone fallback |
| 3 | pip wheel build `No module named 'pkg_resources'` | `openai-whisper==20231117` 是 sdist-only、build isolation 抓 latest setuptools（已 remove pkg_resources） | 移到 `.run_commands` 用 `--no-build-isolation` |
| 4 | Modal edge cache `/breeze/health` 返回舊版 | Cloudflare edge cache 8-15min | `?_cb=` cache buster bypass |

**已寫進 lesson memory**: `lesson_2026-05-22_modal-image-cosyvoice-deps.md`（pending lesson write）

---

## Phase 1 PoC 7 個 MUST artifact 目標狀態

| # | Artifact | 狀態 |
|---|---|---|
| 1 | `audio/t01-t10.wav`（BreezyVoice 廠商台灣女聲） | ⏳ 等 TTS 上線 |
| 2 | `audio/edward_voice_clone_demo.wav`（Edward voice clone） | ⏳ 同上 |
| 3 | `results/round-trip-cer.csv`（vs 7.97%） | ⏳ runner 待跑 |
| 4 | `results/edward-voice-spotcheck.md` | ⏳ runner 待跑（ASR 部分已驗、寫檔在 runner stage 3） |
| 5 | `results/latency.csv` | ⏳ runner 待跑 |
| 6 | `DAY3-COMPLETE.md`（本檔） | ✅ preliminary ship |
| 7 | `CASTLE-DISPATCH-DEMO.md`（FC + dispatch） | ✅ schema + trace + skeleton ship |

**Phase 2 起手 bonus（nice-to-have）**：
- 8: `eagle_enrollment_result.md` ✅ 文檔 ship（待 Edward 申請 AccessKey 才能真註冊）
- 9: `wake_word_setup.md` ✅ 文檔 ship（待 Edward Console 點 1 下訓「蘇菲」）

---

## Edward 起床完整 next-step

讀 `breeze_poc/phase1-poc/EDWARD-WAKE-UP-CHECKLIST.md` —— 1 分鐘看完整局。

**最壞情況**：TTS image rebuild 後仍撞牆（cosyvoice runtime 依賴鏈太深）→ Phase 1 verdict 改為「ASR 跑通且品質可驗、TTS 卡 dependency hell」→ Edward 拍板 A/B/C：
- A. 換 TTS（不用 BreezyVoice、用 Edge-TTS / Azure / 自架 XTTS-v2 等替代）
- B. 投資 Modal A10G image 額外 1-2 天 debug
- C. archive Phase 1、保留 OpenAI Realtime

當前狀態：image fix in flight、不該 escalate、等 deploy result 再判。

---

## 雙軌工時校準（卡西法 Day 3 凌晨段）

- **預估**：Day 3 mid-progress 8 hr（資深工程師、AI 輔助）
- **移動城堡**：凌晨 1-3:30 約 2.5 hr，含 4 個 root cause debug + 2 個 fix 試 + 文檔 5 篇 + 多 commit + multiple Modal redeploy（5-10 min each、並行）
- **倍率**：~0.4× total（單 root cause debug + 雙軌 fix 並行最有效率區段；Modal cold start + image build 等待時間佔比 60%、剩 40% 是真實 reasoning time）

---

## 何時 overwrite 本檔

day3_runner.py 跑成功後 → write_day3_complete() 會 overwrite 本檔成 final 版（含真實 CER mean / median / max + latency P50 P95 + escalate 觸發判定）。
