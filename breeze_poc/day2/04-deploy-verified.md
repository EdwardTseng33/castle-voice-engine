# Day 2 Deploy Verified（5/22 卡西法 全自治 完成）

## ✅ Deploy + Smoke 全綠

### Modal App live
- **App name**：`castle-voice-engine-breeze-poc`
- **Endpoint**：`https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run`
- **跟現役並存零污染**：現役 `castle-voice-engine`（OpenAI Realtime）不同 app name、互不影響
- **Image cache**：121s 第二次 rebuild（加 python-multipart）、之後 redeploy 3s

### /breeze/health smoke
```
GET https://.../breeze/health
HTTP 200 in 0.97s
{
  "status": "ok",
  "version": "0.1.0-day1",
  "day": 1,
  "stack": "breeze",
  "note": "ffmpeg / pydub / torch 已安裝、ASR/TTS 待 Day 2 接上",
  "isolation_check": {
    "modal_volume_attached": false,   ← Gate 5 條件 1 ✅ 真驗證
    "audio_persisted": false
  }
}
```

### Gate 5 條件 5 · 401 wall 真實驗證
```
POST /breeze/audio/preprocess with X-Breeze-Token: WRONG_TOKEN
HTTP 401 in 8.84s
{"detail":"Edward 個人 token 不符 / 拒絕"}
```
✅ 個人 token gate 正確守護、非 Edward 不得用

## Day 2 開跑期間共撞 4 個問題、全自治修

| # | 問題 | Root cause | Fix |
|---|---|---|---|
| 1 | `add_local_dir("../castle", ...)` 路徑錯 | castle root 在 Moving Castle/、不是 sibling | 拿掉、Day 7-8 接 subagent 時改正確路徑加回 |
| 2 | Windows cp950 console 撞 rich UTF-8 box-drawing | Modal CLI 1.4.2 + Win10 cp950 | export `PYTHONIOENCODING=utf-8` |
| 3 | `python-multipart` not installed | Day 1 ship 漏裝、UploadFile = File(...) 必需 | 加進 `.pip_install` |
| 4 | FastAPI 0.115 ForwardRef('UploadFile') 撞 dependency resolver | `from __future__ import annotations` 把 type hint stringify | 拿掉 future import + 用無 type hint 寫法 |

## ⏳ Pending Edward 動作（再給我一個 token 訊息就能接 ASR）

**Edward 5/22 已建好 `breeze-poc-auth` secret（5/22 01:49 confirmed）**

我接 Day 2 Breeze-ASR-25 還缺 1 件：實際 token value 跑 m4a → WAV 整套流程。
Modal CLI 不允許 print secret value（保護設計）、Edward 跑 Step 1 時 PowerShell `$token` 印過、應該存了。

請 Edward 下次給我 prompt 時、附一句：「BREEZE_AUTH_TOKEN=abc123...」
（或更安全：放 `castle-voice-engine\.env` 加進 `.gitignore`、卡西法讀本機 .env）

選 .env 做法更乾淨，我寫 `.env.example` + `.gitignore` 補強。

## Day 2 接下來（拿到 token 後）

1. 測 `/breeze/audio/preprocess` 用 voice_samples/edward_for_eagle.m4a → WAV bytes ✓
2. 在 image 加 transformers `MediaTek-Research/Breeze-ASR-25` auto-download
3. 寫 `/breeze/asr/transcribe` endpoint（接 Day 1 preprocess output）
4. Edward 用手機錄 10 句 t01-t10.m4a（test set 在 `day2/01-breeze-asr-25-research.md`）
5. 跑全 10 句 transcribe → 算 CER → vs 廠商 7.97%
6. 寫 Day 2 final report

## Day 3-10 計畫不變

- Day 3-4：BreezyVoice TTS + 1 段樣本 + 延遲量測
- Day 5-6：Picovoice Eagle 註冊（edward_for_eagle.m4a 1.56MB 60-90s OK）
- Day 7-8：Claude function calling 接城堡 7 subagent
- Day 9-10：端到端 demo + Final report

## Modal cost monitoring

- Deploy ≠ active GPU（function scaledown_window=60、idle 1min 就 sleep）
- 至今 cost 估 < $0.20（4 次 image build CPU + 5 次 cold start CPU、無 GPU active）
- escalate 觸發點：PoC 期 > $50（充足裕度）
