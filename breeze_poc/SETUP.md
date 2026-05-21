# Voice Path v2.0 Breeze PoC · SETUP

> Day 2 開跑前置已由卡西法自治處理（5/22）、見「Day 2 fix」段
> Day 1 完整內容保留在「Day 1 ship」段不變

---

## Day 2 fix（卡西法 5/22 自治處理）

### Fix 1 · 路徑修正（已 commit）
`app_breeze.py` line 43 `add_local_dir("../castle", ...)` → 拿掉。
原因：`castle-voice-engine/../castle` 不存在（castle root 在 `C:\Users\Administrator\Claude\Moving Castle\`、不是 sibling）。
Day 7-8 接 Claude function calling 派 subagent 時、改成正確路徑加回：
```python
.add_local_dir("../Moving Castle", remote_path="/root/castle")
```

### Fix 2 · Windows cp950 編碼 workaround
Modal CLI 1.4.2 + Win10 cp950 console codepage 撞 rich progress bar UTF-8 box-drawing 字符。
解：deploy 前 set `PYTHONIOENCODING=utf-8`：
```powershell
$env:PYTHONIOENCODING="utf-8"
py -m modal deploy breeze_poc/app_breeze.py
```

### Fix 3 · Deploy 已成功（Modal 端 image build OK）
- Modal App：`castle-voice-engine-breeze-poc` ✅ deployed（5/22）
- Endpoint：`https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run`
- Image build：113s（ffmpeg + torch 2.4.1 + transformers 5.9.0 + librosa 0.11 + soundfile）
- 跟現役 `castle-voice-engine`（OpenAI Realtime）並存零污染、不同 app name

### Status（5/22 等待 Edward Step 1）
- ⏳ `breeze-poc-auth` secret 待 Edward 跑 PowerShell 3 行（見 Day 1 Step 1）
- 等 secret ready → 卡西法 retry deploy → /health smoke → 開 Day 2 ASR

---

## Day 1 ship（原始內容保留）

# Voice Path v2.0 PoC · Day 1 收尾 + Edward 動作清單

> Day 1 卡西法 ship: PLAN.md + app_breeze.py skeleton + cleanup_modal_volume.py + register_eagle_speaker.py stub
> Branch: `voice-path/v2.0-breeze-poc` (隔離、castle/main 零污染)

## Edward 半夜不必動 / 醒了 1 步開跑

### Step 1 (1 min) · 建 Modal secret
```powershell
# PowerShell
$token = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
py -m modal secret create breeze-poc-auth BREEZE_AUTH_TOKEN=$token
$token  # 印出來、複製存好 (要打 /breeze/* endpoint 時帶 X-Breeze-Token header)
```

### Step 2 (回卡西法 Slack / 主對話蘇菲)
回一句 "Day 2 開跑" 卡西法就會:
1. `cd castle-voice-engine`
2. `py -m modal deploy breeze_poc/app_breeze.py`
3. cold start 等 image build (~3-5 min · ffmpeg + torch + transformers)
4. 拿到 `https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run`
5. 跑 m4a → WAV 轉檔測試 (用 voice_samples/edward_for_eagle.m4a)
6. 開始 Day 2 任務 (Breeze-ASR-25 download + 10 句 ASR 測試)

## Day 3 mid-progress 預定交付

- ✅ /breeze/health 通
- ✅ /breeze/audio/preprocess 通 (m4a → WAV 16kHz mono、隱私架構符合)
- ✅ /breeze/asr/transcribe 通 (Breeze-ASR-25)
- ✅ 10 句 ASR 中文聽錯率初值 (vs 廠商 7.97%)
- ✅ /breeze/tts/synthesize 通 (BreezyVoice 預設台灣腔女聲)
- ✅ 1 段中文音檔樣本 (給 Edward 聽聽)
- ✅ 延遲量測初值
- ✅ 任何 NO-GO 信號 (escalate 主對話蘇菲)

## 給主對話蘇菲彙報用 (節錄)

> Day 1 ship · 5 deliverable:
>   1. PoC branch `voice-path/v2.0-breeze-poc` 開、castle/main 零污染
>   2. PLAN.md (10 天時程 + Gate 5 五條件 mapping + NO-GO 觸發)
>   3. app_breeze.py skeleton (Modal A10G image + ffmpeg + audio preprocess endpoint + 隱私架構守 Gate 5 條件 1)
>   4. cleanup_modal_volume.py (Edward 1 行驗證腳本、Gate 5 條件 2)
>   5. register_eagle_speaker.py stub (Day 5 開啟)
>
> Edward 動作 (1 min): 建 `breeze-poc-auth` Modal secret (PowerShell 1 行、見 SETUP.md)
> Day 2 開跑: 等主對話蘇菲 / Edward 回 "Day 2 開跑" 後 deploy + 跑 ASR 量測
> Day 3 mid-progress: 預計交 ASR/TTS 樣本音檔 + 延遲量測

## Gate 5 五條件當前狀態

| # | 條件 | 狀態 |
|---|---|---|
| 1 | 聲音樣本 never 寫 Volume | ✅ 架構符合 (tempfile + bytes / 無 Volume 掛載) |
| 2 | PoC 結束 7 天內 Edward 驗零殘留 | ✅ cleanup_modal_volume.py ship、教學在 PLAN |
| 3 | Modal account 2FA | ⚠ Edward 自證 (本 PoC 開跑前自查、Final report 確認) |
| 4 | Modal CLI token < 90 天 | ✅ `.modal.toml` 創於 2026-04-28 = 24 天 |
| 5 | PoC 不接外部 / 不收客戶聲音 | ✅ X-Breeze-Token header 限定 Edward 個人 secret |

## 不在範圍 (再次確認)

- ❌ 不動現役 app.py (零 regression)
- ❌ Phase 2 voice clone (Edward 拍板暫不做)
- ❌ Phase 3 webcam (sulima 未開 Gate)
- ❌ 對外使用者
