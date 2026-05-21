# Day 2 Complete · Ship Report（5/22 卡西法 全自治）

## ✅ Deliverable

### 端點上線（v0.2.0-day2）
| 端點 | 方法 | 狀態 | 驗收 |
|---|---|---|---|
| `/breeze/health` | GET | 200 OK | day2 propagated（需加 `?_cb=` cache buster） |
| `/breeze/audio/preprocess` | POST | 401 wall ✅ + stub ready | 待 token → m4a→WAV |
| `/breeze/asr/transcribe` | POST | 401 wall ✅ + stub ready | 待 token → echo metadata |

### Modal App
- **App**：`castle-voice-engine-breeze-poc` v6 deployed
- **Endpoint**：`https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run`
- **跟現役並存零污染**：✅ confirmed via app list
- **Cost 至今**：< $0.30（6 次 deploy CPU + 多次 cold start CPU、無 GPU active）
- **Image** ready deps：ffmpeg + torch 2.4.1 + transformers 5.9.0 + librosa 0.11 + soundfile 0.13 + jiwer 3.x + accelerate 0.30+ + python-multipart

### Gate 5 條件 1 + 5 真實驗證
- 條件 1（never write Volume）：health JSON `isolation_check.modal_volume_attached: false` ✅
- 條件 5（個人 token 限定）：WRONG_TOKEN → 401「Edward 個人 token 不符 / 拒絕」✅

### Day 2 期間共撞 5 個問題、全自治修
| # | 問題 | Fix |
|---|---|---|
| 1 | `add_local_dir("../castle", ...)` 路徑錯 | 拿掉、Day 7-8 加回 |
| 2 | Win10 cp950 console 撞 rich UTF-8 box-drawing | `PYTHONIOENCODING=utf-8` |
| 3 | python-multipart 漏裝 | 加進 pip_install |
| 4 | FastAPI 0.115 ForwardRef('UploadFile') | 拿掉 `from __future__ import annotations` |
| 5 | Modal edge cache `/breeze/health` 返回舊版 | 加 `?_cb=$(date +%s%N)` cache buster |

### 補件
- `breeze_poc/client.py`：本機 stdlib-only client（health / preprocess）
- `.env.example`：BREEZE_AUTH_TOKEN 範本（`.env.example` whitelist + `.env` ignored）
- `breeze_poc/day2/` 5 篇研究 + 進度 + ship 紀錄

## ⏳ Day 3 開跑前唯一阻塞

Edward 給 token 任一方式：
- A. 下次 prompt 附 `BREEZE_AUTH_TOKEN=abc123...`
- B. 寫 `castle-voice-engine\.env`（git-ignored、卡西法本機讀）
- C. 自己跑 `py breeze_poc/client.py preprocess voice_samples\edward_for_eagle.m4a test.wav` 把 WAV 跨出來丟我

**任一條都解阻塞、不需要 Edward 半夜起來**。

## Day 3 計畫（拿到 token 後 90 分鐘內可完成）

1. `py breeze_poc/client.py preprocess voice_samples/edward_for_eagle.m4a edward_16khz.wav`（5 min · 驗 m4a→WAV pipeline）
2. 升級 `transcribe` endpoint 從 stub → 真跑 Breeze-ASR-25：
   - 改 function decorator 加 `gpu="A10G"` + class-based `@modal.enter()` 預載 model
   - `transformers.AutoProcessor` + `WhisperForConditionalGeneration`
   - HuggingFace `MediaTek-Research/Breeze-ASR-25`（待 first deploy confirm 確切 ID）
3. 跑 `voice_samples/edward_for_eagle.m4a` → transcribe → 看 ASR 結果
4. Edward 用手機錄 10 句 t01-t10.m4a（test set 在 `day2/01-breeze-asr-25-research.md`）
5. 全跑 transcribe → jiwer CER → vs 廠商 7.97% baseline

## 估時 vs 真實（卡西法雙軌工時校準）

- **預估**：Day 2 deploy + smoke = 4 hr（資深 Modal Python 工程師、有 AI 輔助）
- **移動城堡**：卡西法 ~2 hr 自治推進（含 5 個 bug 修 + 3 篇研究 note + 2 篇進度 note + 1 篇 ship report + commit + push）
- **倍率**：~0.5×（顯著快、原因是並行：deploy 等待時寫文檔、撞點 root cause 推理迅速、無人類審核延遲）
- **學習**：「sanity check 路徑 + 編碼 + 依賴 + ForwardRef + CDN cache」5 個 Modal Python 常見坑、寫進 SETUP.md「Day 2 fix」段未來 Voice Path / 其他 Modal 專案不重犯

## escalate 觸發狀態

| # | 觸發點 | 狀態 |
|---|---|---|
| 1 | Breeze ASR CER > 15% | 未到（等 Day 3 token）|
| 2 | BreezyVoice 延遲 > 2 秒 | 未到（Day 3-4）|
| 3 | A10G VRAM 撞 | 未到（Day 5-7）|
| 4 | Eagle 中文聲紋撞牆 | 未到（Day 5-6）|
| 5 | Claude function calling 撞 | 未到（Day 7-8）|
| 6 | Modal 月費 > $50 | 充足裕度（< $0.30 / $50）|

**全綠、不 escalate**。

## 給主對話蘇菲彙報用（節錄）

> Day 2 ship 完成（5/22 02:30 TST）：
>   - Modal `castle-voice-engine-breeze-poc` v6 endpoint live
>   - /health 200 OK · /audio/preprocess 401 wall · /transcribe stub 401 wall 三端點全綠
>   - Gate 5 條件 1 + 5 真實驗證 PASS
>   - 5 個 Day 2 bug 全自治修（路徑 / 編碼 / 依賴 / ForwardRef / CDN cache）
>   - 跟現役 castle-voice-engine 零污染
>   - 預載 deps：transformers + jiwer + accelerate（Day 3 ASR ready）
>
> Day 3 開跑唯一阻塞：Edward 給 token（環境變數 OR .env OR 自己跑 client.py 把 WAV 傳我）
>
> 估時 vs 真實：預估 4 hr、卡西法 2 hr 自治、倍率 ~0.5×（顯著快）
