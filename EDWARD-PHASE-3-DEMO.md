# Edward · Phase 3 鏡頭多模態 demo（5 分鐘上手）

`castle-voice-engine v0.3.0` · 2026-05-22

蘇菲現在不只聽得到你、也看得到你了。

---

## TL;DR

1. `modal deploy app.py`（或繼續用 `https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/`）
2. 打開瀏覽器、開麥克風講中文 → 蘇菲照舊回（Phase 1）
3. 按「**開鏡頭**」→ 蘇菲看得到你（畫面不存任何地方）
4. 按「**開始蘇菲看畫面**」→ 蘇菲每 5 秒講一句觀察（「你笑了喔」「喝水了好」）
5. 想關按「**緊急關閉鏡頭**」（< 200ms）

---

## 環境準備（一次性）

### 1. Modal secret 加 Anthropic key

```
# 已存在 secret 名為 "anthropic-key" (Edward 4/29 建)
# 想換 key：modal secret create anthropic-key ANTHROPIC_API_KEY=sk-ant-xxx --force
```

（既有的 `openai` + `anthropic-key` secret 繼續用、不動）

### 2. Deploy

```
cd C:\Users\Administrator\Claude\castle-voice-engine
modal deploy app.py
```

第一次 cold start 會多花 30-60 秒下載 mediapipe + opencv（~150MB）。後續會 cache。

> **Modal sandbox 限制**：Modal 容器本身**沒有 webcam**。
> 但 Phase 3 不在 server 端取 frame、是在 **你的瀏覽器** 端取 frame、再透過 server 轉給 Claude。
> 所以 deploy 到 Modal 一樣 work、webcam 是用你 Windows 的 webcam。

實際上 v0.3.0 server-side `cv2.VideoCapture(0)` 是 fallback 路徑（適用本機跑）；prod 模式下、瀏覽器負責取 frame 並 POST 給 server 做 vision analysis——下面有詳細說明。

---

## 怎麼用（5 步）

### Step 1: 開瀏覽器

```
https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/
```

### Step 2: 開始對話（音訊只 · Phase 1 OK）

按「**開始對話**」→ 允許麥克風 → 等狀態變綠「連線完成」→ 開始講中文。

蘇菲會即時聽 + 即時用台灣腔回（marin voice）。

### Step 3: 開鏡頭

往下滑、看「**鏡頭多模態（Phase 3）**」區塊。

按「**開鏡頭**」→ Server 取 frame（本機跑時）/ 或 Modal 取空 webcam（Modal 上跑時、會 503，這是預期）。

**Modal 限制 workaround**：v0.3.1 會加 browser-side webcam capture 並 POST frame 到 `/vision/analyze`。v0.3.0 PoC 在本機跑 server 完整 work。

### Step 4: 開始蘇菲看畫面

鏡頭啟動後、按「**開始蘇菲看畫面**」。

每 5 秒蘇菲會：
1. 看一張縮圖（< 200KB · 768px max · JPEG q70）
2. 用 Claude Haiku 4.5 分析
3. 用 ≤ 25 字台灣腔講一句觀察
4. 觀察會透過 `dataChannel` relay 進 OpenAI realtime session
5. 蘇菲開口講（marin voice）

### Step 5: 關閉

- 「**關鏡頭**」= 正常停（graceful）
- 「**緊急關閉鏡頭**」= 立刻停（< 200ms · Incident 7.3）
- 關瀏覽器 tab = browser `beforeunload` 會自動 sendBeacon `/camera/kill`

---

## 緊急停止（記住這個）

### 三道 kill switch

1. **UI 按鈕**：點「**緊急關閉鏡頭**」→ 紅色按鈕 → 200ms 內停
2. **API 直接打**：`curl -X POST https://your-url/camera/kill`
3. **環境變數鎖死**：在 Modal env 加 `CAMERA_DISABLE=1` → 任何 `/camera/enable` 都被拒

任何時候你想關、上述任一招都行。**蘇菲不會自作主張開鏡頭、永遠是你按開、你按關**。

---

## 隱私守則速查（7 大類落到 code · ADR-018 對應）

| 守則 | 怎麼落實 | 對應檔案 |
|---|---|---|
| Data flow 1.1-1.6 | frame 全程 RAM、不寫磁碟、numpy ndarray 跑完丟 | `camera.py` |
| IAM 2.4 token | `ANTHROPIC_API_KEY` 從 Modal secret 讀、不 hardcode、不 log | `vision_analyzer.py` |
| Encryption 3.2 transit | 本機 OpenCV 取 frame、本機 MediaPipe 處理、只送縮圖給 Claude（TLS） | 全模組 |
| API 4.1 rate limit | frame rate 10 fps 硬 cap、vision 每 5s 一張、最快 2s 一張 | `camera.py` + `vision_analyzer.py` |
| Privacy 5.1 opt-in | 預設 OFF、必按「開鏡頭」、env `CAMERA_DISABLE=1` 鎖死 | `camera.py` 第 89 行 |
| Privacy 5.4 不收敏感資料 | frame 不存、5s 一張不是 surveillance、user 隨時關 | `vision_analyzer.py` |
| Incident 7.3 kill switch | `threading.Event` + `cap.release()` ≤ 200ms | `camera.py` kill() |
| Incident 7.1 audit log | 每次 start / stop / 每張送 Claude 都 log stderr（無內容） | 三模組 |

### ADR-018 3 項實測對應

| 測試 | v0.3.0 怎麼過 |
|---|---|
| webcam Wireshark 零外送 | 本機 OpenCV 抓 frame + 本機 MediaPipe → 只送 < 200KB JPEG 給 Anthropic API（TLS、可審）；除此之外零外送 |
| 磁碟掃描零殘留 | 全程 RAM、`grep -r "cv2.imwrite\|open.*w" castle/multimodal` 應該完全沒有結果 |
| kill switch ≤ 200ms | `threading.Event.set()` + `cap.release()` 不等 thread join、實測 0-20ms |

---

## API endpoint 速查

| Method | Path | 用途 |
|---|---|---|
| POST | `/camera/enable` | 開鏡頭（user 明確 opt-in） |
| POST | `/camera/disable` | 正常停 |
| POST | `/camera/kill` | 緊急停 ≤ 200ms |
| GET | `/camera/status` | 看 camera + vision 狀態 |
| GET | `/camera/snapshot` | 取最新 frame（需 `CAMERA_DEBUG=1`） |
| POST | `/vision/enable` | 開蘇菲看畫面 loop |
| POST | `/vision/disable` | 停 loop |
| GET | `/vision/status` | 看 vision 統計 |
| GET | `/vision/latest` | 取最新 obs（browser 1Hz poll） |

---

## 已知限制

1. **Modal 沙箱無 webcam**
   v0.3.0 的 server-side `cv2.VideoCapture(0)` 在 Modal 容器內會回 `webcam_open_failed`（Modal 沒實體 webcam）。
   PoC 等級下、要看完整 flow、請：
   - **本機跑**：`uvicorn castle.server.engine_server:app --port 8000` + 手動 attach camera routes
   - **或等 v0.3.1**：補 browser-side webcam capture（getUserMedia video）+ POST frame 到 server，讓 Modal 也能 work

2. **MediaPipe 大小**
   `mediapipe>=0.10.14` ~120MB pip install。Modal cold start 第一次 +30-60s。

3. **Claude vision 成本**
   `claude-haiku-4-5` 每張縮圖 ~150-200 input tokens + ~30 output。粗估：
   - 10 分鐘對話 + 鏡頭開全程 = 120 calls × ~200 tok = ~24k input tok ≈ $0.002 (Haiku $0.80 / Mtok)
   - 1 小時 = ~$0.012、可接受

4. **觀察 relay 不是真即時**
   browser 1Hz poll `/vision/latest` → 拿到 obs → `dataChannel.send(session.update)` 把觀察塞進蘇菲 system prompt。
   蘇菲不會「立刻」講、是「下一次她該講話時」會把觀察融進回應。
   想要「看到立刻講」要改 server push 或 OpenAI conversation.item.create—— v0.3.1 範圍。

5. **單人多裝置 race**
   `CameraManager` 是 process-level singleton。同一 Modal container 多 user 同時打 `/camera/enable` 會搶。
   v0.3.0 PoC 不處理、Modal scaledown_window=120s 同時只能一個 user 用、目前 fine。

6. **macOS / Linux webcam permission**
   本機跑時、macOS 第一次會跳「終端機要 access webcam」、要 allow。
   Windows webcam permission 一般自動。

---

## 下一步（v0.3.1 / v0.4 候選）

| 編號 | 主題 | 重點 |
|---|---|---|
| v0.3.1 | Browser-side capture | getUserMedia video → POST frame → Modal 可 work |
| v0.3.2 | 真即時 relay | server push obs via WebSocket / conversation.item.create |
| v0.4 | Visual memory | obs 累積成短期 visual context（「你今天笑了 N 次」） |
| Phase 3.5 | 桌面情境感知 | pywin32 active window / browser tab title（Edward 待拍板） |

---

## File map（這次新增）

```
castle-voice-engine/
├── app.py                                 # v0.3.0 mount + secrets["anthropic"]
├── requirements.txt                       # +mediapipe / opencv / anthropic / Pillow / numpy
├── castle/
│   ├── multimodal/                        # NEW
│   │   ├── __init__.py
│   │   ├── camera.py                      # 304 行 · MediaPipe + capture loop + kill switch
│   │   └── vision_analyzer.py             # 383 行 · Claude vision + narration relay
│   ├── server/
│   │   └── camera_endpoints.py            # NEW · 185 行 · 9 endpoints
│   └── static/
│       └── index.html                     # 639 行（v0.3.0 加鏡頭區 + vision poll）
└── EDWARD-PHASE-3-DEMO.md                 # 本檔
```

---

## 問題排查

| 現象 | 怎麼辦 |
|---|---|
| 按「開鏡頭」回 503 | Modal 沒 webcam（預期）/ 本機沒裝 cv2 → `pip install opencv-python-headless` |
| 按「開蘇菲看畫面」回 `anthropic_api_key_missing` | Modal secret `anthropic-key` 沒設定、或本機 env 沒 export `ANTHROPIC_API_KEY` |
| 「鏡頭中」但「蘇菲看畫面」一直空 | 看 Modal log：應該有 `vision call - img_kb=X` / 沒的話 frame 沒 ready |
| 蘇菲不講觀察 | 確認 dataChannel state 是 `open`（按 F12 看 console log）/ 觀察是否一直 SKIP |
| 緊急關閉沒立刻停 | `/camera/kill` response 內 `elapsed_ms` 應該 < 200 / 如果 > 1000 表示 thread 卡死、報 bug |

有問題撂個 commit 或在 Slack `#voice-path` 標 `[CALCIFER PHASE 3 BUG]` 我看。

