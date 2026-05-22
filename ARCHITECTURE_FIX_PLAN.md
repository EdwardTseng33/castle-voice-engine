# Voice Path 架構修正 + 自架路徑計畫

> 2026-05-23 凌晨 Edward 點破「我們語音服務不是用的是 GPT 的 realtime2 嗎」+ 拍板三層分工
> 後續 Edward 拍板「跳 v0.6 直接 v0.7-0.8 中期前進、找現成女性直接用」

## Edward 三層架構拍板 (2026-05-23 凌晨)

| 層 | 工具 | 狀態 |
|---|---|---|
| **聽** (用戶語音 → 文字) | MediaTek-Research/Breeze-ASR-25 (退路 ASR-26) | ✅ Phase 1 PoC 5/22 calcifer 已部署 Modal app `castle-voice-engine-breeze-poc` · 認證 `BREEZE_AUTH_TOKEN` |
| **說** (對話 + 語音生成) | OpenAI gpt-realtime-2 (marin 中文暖嗓 + 蘇菲人設) | ✅ v0.3.x backend 已寫 · `castle/server/realtime_endpoints.py` |
| **嘴** (真人臉嘴對齊) | 短期 Tavus Phoenix-4 echo / 中期 MuseTalk 自架 / 長期 MuseTalk + Sophie 微調 | ⚠️ 短期 Tavus 通 · 中長期跨出 Tavus |

完整流程：
```
用戶講話 → Breeze ASR-25 (Modal 後台) → 台灣腔中文文字
   ↓
GPT realtime-2 (conversation.item.create 送文字 + response.create 拿 audio)
  · 蘇菲人設 (不超 25 字 / 禁反問 / 台灣腔)
  · marin 暖嗓中文聲
   ↓
中文蘇菲聲音
   ↓
talking head 嘴對齊模型 (Tavus echo 短期 / MuseTalk 中期)
   ↓
用戶看到: 真人臉 + 嘴對齊中文 + 蘇菲人設
```

## Edward 5/23 拍板「跳 v0.6 直衝 v0.7-0.8」+ Tavus 月費不實際 catch

5/23 深夜 Edward 看到 Tavus Plus 定價 $20/月 = **150 分鐘對話上限**:
- 一天用蘇菲 2 小時 = 1.25 天爆額度
- 一天用 5 小時 = 半天爆
- 「蘇菲作為主要工作媒介窗口的話、一天最少就要幾個小時、所以有點不切實際」
- Tavus 高階方案 $200-1000+/月才足量、商業化才划算

對外場景 (會議 / 訪談 / 代理人) 流量更大 = Tavus 月費直接破局。

**真實月費對比** (Edward 真實用量 60 hr/月):

| 方案 | 月費 | 時長上限 | 撐多久 |
|---|---|---|---|
| Tavus Plus | $20 | 150 分鐘 | 1.25 天爆 |
| Tavus 高階 | $200-1000+ | 看方案 | 可能但貴 |
| Duix | Tavus + 30% | 類似 | 一樣不夠 |
| **MuseTalk 自架 Modal A10G** | **≈ $66** | **無上限** | 多用多省 |
| LiveAvatar 自架 Modal H100 | ≈ $330 | 無上限 | 品質好但燒 |

= **v0.6 Tavus 三層整合完全砍掉、不做**。直接 v0.7 MuseTalk 自架為唯一主路、為對外場景準備真正自有資產。

## 三張 Sophie 視覺資產盤點

| 檔案 | 描述 | 適合 MuseTalk |
|---|---|---|
| `castle-voice-engine/assets/sophie_reference.png` (2.16 MB · 5/22 Edward 親選) | 銀灰髮編辮 + 粉紅蝴蝶結 + 藍色高領 + 暖琥珀紅底 · 半寫實 AI | ⚠️ 半寫實風 · 編辮裝飾可能干擾臉部特徵點 |
| `Moving Castle/public/assets/sophie-portrait-original.png` | 銀灰短髮 + 藍色高領 + 藍底 · 接近寫實 AI | ✅ 比編辮版更接近寫實、預期效果好 |
| `Moving Castle/assets/agent-icons/sophie_avatar.png` | Q 版漫畫頭像 | ❌ 純漫畫 · 不能用於 talking head |

## v0.7 路徑 · 自家後台 MuseTalk + 待機 / 啟動切換設計

### v0.7 Step 1-3 整合工時

| Step | 內容 | 工時 (移動城堡) | 成本 |
|---|---|---|---|
| 1 | 線上試用版 (HuggingFace Space) 上傳兩張 Sophie + 中文 audio · 看嘴對齊品質 | 30 min | 免費 |
| 2-A 路通 | 部署 MuseTalk 到 Modal A10G ($1.10/hr) + 接三層整合 | 15-25 hr | 顯卡跑時計費 |
| 2-B 路不通 | 用 Stable Diffusion / DALL-E 生「寫實版蘇菲」候選 3-5 張 · Edward 挑 · 無版權 | 1 hr 生圖 + Edward 5 min 挑 | 免費 (open model) |
| 3 | 接通整套: 聽 Breeze + 說 GPT realtime + 嘴 MuseTalk + UI Duix 範式 | 含 step 2 內 | - |
| 4 | 待機 / 啟動切換 (見下方 A-E 設計) | 5-8 hr | 本機跑 · 不燒 Modal |

### v0.7 待機 / 啟動切換完整設計 (Edward 5/23 拍板)

#### A. 待機狀態 (不燒運算、瀏覽器本機跑)

利用 Phase 2 後半段已寫的骨架 (5/21 Edward 拍板「本機跑、不上雲」):

| 工具 | 跑哪 | 工作 |
|---|---|---|
| Picovoice Porcupine 中文喚醒詞 | 瀏覽器本機 | 持續監聽「嘿蘇菲」/「蘇菲」 |
| SpeechBrain 聲紋認證 (主路) | 瀏覽器本機 | 喚醒詞觸發後驗證是 Edward 本人 |
| MediaPipe 臉偵測 | 瀏覽器本機 | 偵測「有人在看螢幕」輔助喚醒 |
| Modal GPU 容器 | 後台 | **全部 scaledown 關閉、$0 計費** |
| Modal CPU 容器 (健康檢查 + 喚醒詞收訊端點) | 後台 | 極輕量、 < $1/月 |

待機畫面: 蘇菲靜態照片 / 暖琥珀 orb 脈衝 + 「叫我或對我看一眼就會醒」提示。

#### B. 啟動觸發 (兩條件擇一)

1. **喚醒詞**: 「嘿蘇菲」/「蘇菲」+ 聲紋確認是 Edward (防家人 / 訪客誤觸)
2. **視訊喚醒**: 鏡頭偵測有人在看螢幕 ≥ 3 秒 (防誤觸發 · 路過不喚)

觸發後動作:
- 客戶端送 wake POST `/voice/wake` → 後台喚醒 GPU 容器 (MuseTalk 預載 5-8 秒)
- 連線 OpenAI realtime WebRTC + Breeze ASR
- 啟動真人視訊嘴對齊 (Daily.co callObject 或 MuseTalk 直接 streaming)
- 蘇菲招呼: 「嗯、我在」

#### C. 自動回待機 (軟降階梯)

| 觸發條件 | 動作 |
|---|---|
| 無對話 30 秒 (OpenAI realtime 內建 turn_detection silence_duration_ms) | 顯示「我在這、有事再叫」字幕 · 不關容器 |
| 無對話 60 秒 + 鏡頭無人 30 秒 | 軟降: 暫停顯卡 (callObject.leave 但保留 conversation_id) · 保留本機喚醒詞偵測 |
| 軟降後再過 5 分鐘無喚醒 | 完全休眠: 後台容器 scaledown · 介面回 A 待機 |

#### D. 真實月費估算 (Edward 真實用量 60 hr/月對話)

- 對話運算 = 60 hr × Modal A10G $1.10/hr = **$66**
- 待機健康檢查 / 喚醒詞收訊端點 = < $1
- 顯卡冷啟動 overhead (每次喚醒首次推論慢 3-5 秒) = 含在內
- **總計 ≈ $67/月** (vs Tavus Plus $20/150 分鐘根本不夠用)

#### E. 視覺切換層次 (純黑 Duix 範式 · 5/23 Edward 拍板暖琥珀全砍)

**最終視覺規格** (跟 BeyondPath 暖琥珀 DNA 完全解綁):

| 位置 | 通話前 | 通話中 |
|---|---|---|
| 整體背景 | **純黑 `#000`** · 無漸層 · 無暖琥珀 | 純黑 |
| 視訊區 | 真人視訊大放中央 (letterbox 上下黑邊兩側) | 同 |
| top-left | 「蘇菲 ⓘ」白字 italic 極簡 | 同 |
| top-right | 空 | 空 |
| bottom-left | 空 | 「02:21」白字 timer (tabular-nums) |
| bottom-center | 綠色電話圓鈕「Start video chat」單一 | 三圓鈕: 🎙 mic / 📷 camera-off / 🔴 結束 |
| bottom-right | 「Powered by 城堡」極淡白字浮水印 | 同 |

**砍掉清單** (從所有舊 plan 移除):
- ❌ 暖琥珀色階 `--amber` / `--amber-deep` / `--amber-bright` 全部
- ❌ 暖琥珀脈衝 orb 動畫
- ❌ 暖琥珀漸層背景 `radial-gradient(... #1a120c ...)`
- ❌ 「今天想跟蘇菲聊什麼？」標題文案
- ❌ 「按下方按鈕、允許麥克風」說明文
- ❌ Avatars 切換 / 語言切換 / Create AI avatar / chat 訊息圖示

**保留**:
- ✅ 純黑底
- ✅ 真人視訊全屏 (letterbox aspect-ratio 對齊 Duix · 視訊區佔約 80% 中央、左右黑邊收 10%)
- ✅ 蘇菲名 italic top-left
- ✅ timer 左下、watermark 右下
- ✅ 綠 / 紅圓鈕

**視覺切換完整流程** (暖琥珀全替換成蘇菲靜態真人照):

```
完全休眠 (5 min 後) → 蘇菲靜態真人照置中 + 「叫我」白字小提示 · GPU 容器關
   ↓ 喚醒詞 / 鏡頭偵測有人
喚醒中 (5-8 秒) → 蘇菲靜態真人照 + 載入小轉圈白色 + 「準備中」白字 · GPU 容器啟動
   ↓ 後台 ready · MuseTalk 載入完
通話前 (replica 揮手 idle) → 真人視訊揮手動態 + bottom 綠色「Start video chat」單鈕 · GPU 100%
   ↓ 用戶點綠鈕 + 開麥
對話進行中 → 真人視訊 + 嘴對齊 + bottom 3 圓鈕 (mic / cam / 結束) · timer 跑 · GPU 100%
   ↓ 30 秒無對話
軟降提示 → 真人視訊 + 字幕「我在這、有事再叫」 · GPU 100% (防誤判)
   ↓ 60 秒無對話 + 鏡頭無人
半待機 → 蘇菲靜態真人照 + 「按一下再叫」白字 · GPU 暫停 (callObject.leave · conversation 保留)
   ↓ 5 分鐘無喚醒
回完全休眠 → A 狀態
```

#### F. Phase 2 既有骨架對接

castle/integrations/__init__.py 已 export:
- `PicovoiceConfig` / `init_porcupine` / `init_eagle_recognizer` (中文喚醒詞 + 聲紋 archived · enterprise 版才能用)
- `SpeechBrainConfig` / `is_speechbrain_ready` / `enroll_speaker` / `verify_speaker` (聲紋認證 · 主路 · 5/22 ship)
- `SpacyNerConfig` / `redact_pii` (個資遮罩 · 在 Phase 1 ASR 文字過個資)

v0.7 整合方式:
- 喚醒詞: Picovoice 個人版額度 (Edward 申請過 AccessKey) OR 改用 Open Whisper-AT (open VAD + keyword spotting)
- 聲紋: SpeechBrain 已 ship · 直接接
- 個資: spaCy NER · 在 ASR 文字輸出後過一遍才送 GPT realtime

### v0.7 Step 4 工時拆解 (5-8 hr)

- 客戶端 Porcupine / SpeechBrain / MediaPipe 整合到 index.html: 2 hr
- 後台 `/voice/wake` + `/voice/sleep` 端點: 1 hr
- 軟降階梯邏輯 (30s / 60s / 5min) 跟 OpenAI realtime turn_detection 整合: 1 hr
- 視覺切換 5 層 CSS / JS state machine: 1 hr
- chrome 全程實測 (待機 / 喚醒 / 對話 / 軟降 / 回待機 5 步): 1 hr
- 紀錄成本實測 + 確認 $67/月真實對齊: 30 min

### G. 響應式 + PWA + 浮窗模式 (Edward 5/23 拍板「能縮成手機 / 不佔螢幕」)

#### G.1 響應式 5 個視窗尺寸 (5/23 Edward 拍板手機基準 iPhone 16 系列)

| 場景 | 視窗尺寸 | 介面行為 |
|---|---|---|
| 桌面全屏 | 1920×1080 | 真人視訊大放 letterbox + 完整工具列 |
| 桌面中等視窗 | 800×600 | 視訊縮 80% + 工具列縮 icon + 字小 |
| 桌面浮窗 (PIP) | 320×240 浮在任何視窗上 | 只剩視訊 + 紅色結束鈕 · 無其他 chrome |
| 平板直立 | 768×1024 (iPad mini ~ Air) | letterbox 轉直 + 底部 toolbar |
| **手機 (iPhone 16 系列)** | **主基準 393×852 (iPhone 16 標準)** · 上限 440×956 (16 Pro Max) | 全屏視訊 + 3 鈕極簡 + iOS safe area 處理 |

CSS 實作:
- viewport-based units (`vw`/`vh`) + `@media` breakpoints + `@media (orientation)`
- iPhone 16 系列 4 機型對應 breakpoint:
  - iPhone 16 標準: 393×852
  - iPhone 16 Plus: 430×932
  - iPhone 16 Pro: 402×874 (Dynamic Island)
  - iPhone 16 Pro Max: 440×956

#### G.1.5 iOS Safari 細節 (iPhone 16 系列)

**Dynamic Island 避開** (16 標準 / 16 Pro / 16 Pro Max 都有):
- Dynamic Island 位置: 頂部正中央 · 37px 高 · 122px 寬 · 距 top 11px
- 蘇菲名 top-left 自然避開 (靠左對齊)
- 視訊區頂部留 60px buffer (safe area-inset-top 自動帶)

**螢幕安全區 CSS** (iOS Safari 業界寫法):
```css
.top    { padding-top: max(20px, env(safe-area-inset-top)); }
.bottom { padding-bottom: max(20px, env(safe-area-inset-bottom)); }
```

**Viewport meta tag** (才會延伸到 Dynamic Island 後面 · 視訊真的吃滿整螢幕):
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
```

**底部 Home indicator buffer** (34px):
- 工具列圓鈕不能被 Home indicator 線壓到
- `padding-bottom: env(safe-area-inset-bottom)` 自動處理

#### G.2 Picture-in-Picture 浮窗模式 (不佔主螢幕的核心)

HTML video element 內建 `requestPictureInPicture()` API:
- 工具列加「最小化」按鈕 → 觸發 `tavusVideo.requestPictureInPicture()`
- 蘇菲視訊浮在桌面角落 200×150 / 可調
- **跨應用永遠在最上方** (VS Code / Slack / 任何工具開著都浮著)
- 用戶可拖移 + resize (瀏覽器原生支援)
- 工作時瞄一眼就在、需要說話再點放大

工時: +2 hr (含 chrome 全程實測 · PIP API 跨瀏覽器相容性確認)

#### G.3 PWA 化 (一鍵安裝成桌面 app)

加兩個檔案讓 Chrome / Edge 支援「安裝為應用程式」:

`castle/static/manifest.json`:
```json
{
  "name": "蘇菲",
  "short_name": "蘇菲",
  "display": "standalone",
  "background_color": "#000000",
  "theme_color": "#000000",
  "start_url": "/static/index.html",
  "icons": [
    {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

`castle/static/sw.js` (Service Worker):
- 快取喚醒詞偵測模型 (Porcupine 本機)
- offline 支援待機畫面 (網路斷蘇菲也在)
- 喚醒後才連後台 (Modal)

安裝效果:
- 桌面 / 開始選單出現獨立「蘇菲」icon (用 sophie_avatar.png 各尺寸)
- 點開 = 獨立視窗、無瀏覽器分頁 chrome、像 native app
- 視窗大小用戶自己拉
- 跟 VS Code / Slack 一樣是獨立桌面應用

工時: +3 hr (manifest + service worker + icon 生成 + Chrome / Edge 兩瀏覽器實測)

#### G.4 長期: Electron / Tauri 原生桌面 app

留 v0.8 之後 (PWA 用一陣子覺得有限制再升級):
- 系統托盤 icon (常駐右下)
- 全域熱鍵 (Cmd+Shift+S 喚醒蘇菲、不必先 focus 視窗)
- 開機自動跑
- 跨平台 (Mac / Windows / Linux)

工時: 30-50 hr (大改寫、不必短期做)

#### G.5 v0.7 介面工時更新

原 v0.7 Step 4 = 5-8 hr → 加 G.1 響應式 (含在 CSS 內) + G.2 PIP +2 hr + G.3 PWA +3 hr = **總 10-13 hr**

**5/22 SoulX-FlashHead 9 次部署失敗的教訓必避免**:
- 先驗 Modal 容器 image 配對 (CUDA / Python / wheel) 才寫整合代碼
- MuseTalk requirements 已讀過 · 沒 flash-attn dependency · 卡點預期較少
- 顯卡選 A10G (V100 等級即可) · 不衝 H100

## v0.8 路徑 · Sophie 微調個人化 (長期)

需要的素材：
- 拍 30 秒 Sophie 真人短片 (或 AI 生成 vid avatar 替代)
- MuseTalk 訓練代碼 (2025/4/5 已開源 · 可用)

工時：30-50 hr 微調 + 顯卡訓練 $60-100 USD

結果：Sophie 自己的臉 + 不依賴 Tavus 任何月費 + 對外丟得出去的真分身

## v0.9 路徑 (可選) · LiveAvatar 品質升級

LiveAvatar (Alibaba Quark · 14B 擴散大模型):
- 45 FPS 即時 / 48GB 顯卡跑 (FP8 量化 · v1.1) / Modal H100 ($5.50/hr)
- 訓練代碼還沒釋出 (v1.2 todo)
- 品質接近 Tavus Phoenix-4 商用水準

觸發條件: MuseTalk 品質 Edward 不滿意 + LiveAvatar v1.2 訓練代碼出來。

## Tavus 開源狀態確認 (5/23)

`github.com/tavus-engineering` org 翻完 = **Tavus 核心 Phoenix-4 模型不開源**、他們 org 只 host：
- 對外整合範例 (tavus-examples / vibecode-quickstart)
- 他們 fork 收藏的別人 TTS 模型 (ZipVoice / Chatterbox / VoxCPM / VibeVoice / Cartesia)

結論: 用 Tavus = 永遠付月費 + vendor lock-in。對外場景必須跨出。

## 失誤反省 (本 session 累積)

整 session 跨 5/22-23 連續違反同類紀律 **4 次**:

1. **v0.4.0** Tavus 介面醜 ship 沒過 chrome 自審 - Edward catch「為什麼驗收可以驗成這樣」
2. **v0.4.1 hotfix** 兩次 - participant_name 不是合法欄位 / Modal hot cache 沒清 - 沒先 hard-test Tavus body 結構
3. **v0.4.2 / v0.5.0** 一直走 Tavus end-to-end 路 - 沒讀 v0.3.x backend 既有架構 / 沒讀 breeze_poc/ 既有 Phase 1 PoC - Edward catch「我們語音服務不是用的是 GPT realtime2 嗎」
4. **多次** 套人類時間框架 (「明天」「白天」「今晚」) - hook 兩次強制 catch

Root cause 共同:
- **整合外部工具時直接照官方 end-to-end 流程走、沒回去查 project 既有架構整合點**
- = `feedback_third_party_tool_official_docs_first.md` 4 道 gate **要加第 5 道**:
  > **接外部工具前必先讀 project 既有架構 + 既有 PoC + 既有 integration · 不再憑印象拍腦袋 end-to-end**

## 下個 session 開場 SOP 補項

Voice Path session 必讀 (除 v5.4.X 通用 SOP 之外):
1. 本檔 `ARCHITECTURE_FIX_PLAN.md`
2. [project_voice_path_vision.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\project_voice_path_vision.md) (Edward 對外 3 角色定位)
3. [project_voice_path.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\project_voice_path.md) (12 個 ADR)
4. `breeze_poc/PLAN.md` + `breeze_poc/SETUP.md` (Phase 1 ASR + TTS PoC 真實狀態)
5. `castle/server/realtime_endpoints.py` (v0.3.x OpenAI realtime + 蘇菲人設)
6. 本 session handoff: `session-handoff-2026-05-23-夜.md`

## 連結

- v0.5.1 UI shell 寫好但 stash 起來: `git stash list` 找 `v0.5.1-unship-pending-arch-fix`
- v0.3.x OpenAI realtime backend: [castle/server/realtime_endpoints.py](castle/server/realtime_endpoints.py)
- Breeze ASR Phase 1 PoC: [breeze_poc/app_breeze.py](breeze_poc/app_breeze.py)
- Tavus client (含 PIPELINE_ECHO 已 declared): [castle/integrations/tavus_client.py](castle/integrations/tavus_client.py)
- MuseTalk GitHub: https://github.com/TMElyralab/MuseTalk
- MuseTalk HF Space: https://huggingface.co/spaces/TMElyralab/MuseTalk
- LiveAvatar GitHub: https://github.com/Alibaba-Quark/LiveAvatar
- LiveAvatar HF model: https://huggingface.co/Quark-Vision/Live-Avatar
