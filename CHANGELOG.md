# Voice Path Changelog

> 蘇菲對外網址：https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/static/index.html
> 分支：voice-path/v0.7-musetalk-self-host

---

## v1.2.0 (v1.0 GA) · 2026-05-23
- 訪客模式 ship · 不再強制前置登入頁、進站直接看蘇菲 idle 動畫 + UI
- Start 點擊才觸發 Google 登入：whoami 200 → 進通話 · 401 → 彈 in-page GIS modal · 403 → 顯示邀請畫面
- 邀請畫面 · 告知對方剛登入的 email + 「請聯絡 edwardt0303@gmail.com 開放」+ 回到櫥窗按鈕
- middleware · /static/* 整段公開 (UI shell / mp4 / sw.js) · API endpoints (/sdp / /camera / /vision / /memory / /tavus / /session / /personas) 仍守 cookie 認證
- auth_middleware.py · 新增 verify_google_id_token_any() 訪客模式雙軌 verify (allow list 過 / 未過 都回 email · 供邀請畫面 echo)
- /auth/verify response · 403 時加 contact + your_email field · 400 (token 無效) 與 403 (未授權) 區分
- auth.html · 拿掉「只有 Edward 個人 Google 帳號可進入」鎖人文案 · 保留 PWA shortcut 入口 + 未授權也顯示邀請文案
- pre-ship-verify.sh 升級 · /static/index.html / /static/sophie-idle.mp4 預期 200 (公開了) · 新增 check_api_gate 驗 /sdp / /memory/health 沒 cookie 401
- SW CACHE bump v1.1.3 → v1.2.0

## v1.1.2.1 · 2026-05-23
- Anthropic API key resolver 4-name fallback · ANTHROPIC_API_KEY / ANTHROPIC_KEY / anthropic_key / ANTHROPIC 任一命中即用
- Modal Secret env var 命名不對齊時優雅退到空摘要 · 蘇菲招呼語退到 v1.1.1 不阻塞通話
- Edward 一次性設 Modal Secret env var 名後啟用蘇菲完整 v1.1.2 記憶能力

## v1.1.3 · 2026-05-23
- 視訊陪伴節律 · MediaPipe Pose + Hands 全本機真整合（補完 v0.3.0 半完成）
- 揮手 / 撐臉 / 雙手舉 / 離開鏡頭 / 回鏡頭 5 種 body-language state
- 揮手 → 點頭 acknowledgement · 撐臉 → acknowledgement · 雙手舉 → playful
- 離開鏡頭 ≥ 10s → idle 慢節奏（20s 輪播 + 12% stroke-hair 等待感）
- 回鏡頭 → 立刻 greeting 一次（bypass 600s cooldown · 蘇菲 micro-greet）
- 新 castle/multimodal/pose_hands_dispatch.py（249 行 · PoseHandsDispatcher singleton）
- 新 /vision/pose_hands_latest 1Hz client poll endpoint（consumed-on-read · 不污染 vision_analyzer）
- camera.py 每 2nd frame（5 fps）跑 pose/hands dispatcher · 4s 同 state cooldown 去抖
- 4-frame absent debounce 防 MediaPipe 邊緣抖動
- client 直接 emit playAction · 不經 GPT function call（4-token roundtrip 太慢）
- 隱私 · Pose/Hands inference 全本機 Modal A10G · 不送 cloud · ndarray 處理完即丟
- /camera/disable killswitch ≤ 200ms 守則不破（v0.3.0 已驗）
- SW CACHE bump v1.1.2 → v1.1.3

## v1.1.2 · 2026-05-23
- 記憶連續性 · IndexedDB 7 天對話 raw / 30 天蘇菲視角摘要
- 後端 /memory/summarize stateless · Claude Haiku 摘要對話成 {summary, mood, promises}
- 開場招呼語升級 pickGreetingV2 · 帶昨天 promise / mood reference 不裝失憶
- 通話結束自動 summarizeDay(today) + TTL cleanup (raw > 7 天 / summary > 30 天)
- 隱私 · raw 對話只在 browser IndexedDB · 後端不存 · Sally / PII 紅線 inherit prompt 層
- 5/min/email rate limit · ANTHROPIC_API_KEY from Modal Secret
- SW CACHE bump v1.1.1 → v1.1.2 (+ conversation-memory.js precache)

## v1.1.1 · 2026-05-23
- 主動性升級 · 時間感知 + 歷史感知 + 環境感知
- 招呼語三層 fallback：同 session 30 分鐘內回來 = 接續 / 同日重訪 = 短招呼 / 跨日 = 完整池
- 星期感知：週一早「新的一週」/ 週末「不打擾」/ 週五晚「週末來了」
- 歷史感知：lastVisit + totalSessions 寫 localStorage（純前端不踩後端 / 不存對話內容）
- 環境感知：tab 切走 idleRotator 暫停、回前景 12% 機率輕點頭
- 動畫機率時段微調：深夜手勢 6% / 早上 18%
- SW CACHE bump v1.1.0 → v1.1.1（+ session-memory.js precache）

## v0.7.2.1 · 2026-05-23
- 移除左上「蘇菲」名旁邊無功能 i 圖示（純裝飾無點擊事件）
- 補丁清 JS 殘留 reference 防瀏覽器後台錯誤

## v0.8 base · 2026-05-23
- Edward 自製 4 支 vivago.ai 自然律動 loop 進程式庫
  - 待機（永遠播）
  - 講話中（蘇菲開口時切）
  - 收到任務（你剛講完蘇菲收到）
  - 交接任務（對話結束蘇菲接住）
- 規格 1080×1916 9:16 24fps 5.08s
- 「首偵 = 尾偵 = idle 第 1 偵」無縫接回紀律驗證 PASS

## v0.7.2 · 2026-05-23
- 兩個狀態簡化（待機 / 通話中、對齊 Duix Lily 範式）
- video loop 永遠播（網頁開啟就活著）
- Inter sans-serif 字型升級（蘇菲名保留 Georgia italic 識別）
- 5 個按鈕全換 Lucide 風格 SVG 圖示（不再 emoji）
  - 電話 / 麥克風 / 鏡頭 / 浮窗 / 結束
- 漸層光暈商用級按鈕質感（hover 微浮 1px + active scale）
- 水印改「✦ Sophie · AI Companion」
- 桌面 / 手機 app icon 4 個尺寸（從 Vidu loop 抽臉 + 純黑圓底）

## v0.7.1 · 2026-05-23
- **聽不到 bug 修復**：OpenAI Realtime API 5/22 → 5/23 規範變動同步（session 規範 / turn_detection / voice 三層搬位）
- **9:16 直式手機滿屏**：iPhone 16 系列 4 機型 + Dynamic Island 安全區
- **Vidu AI 1080×1920 loop** 替換 Phase 7a 嘴對齊 mp4（解析度 4 倍提升 + 自然轉頭動作）
- **Vidu 無水印備案**（1080×1824 OpenCV 程式裁切版、未來 Track B 對外用）

## v0.7 · 2026-05-23
- **三層架構上線**：
  - 聽 = Breeze ASR-25（聯發科開源 · Modal A10G）
  - 說 = OpenAI gpt-realtime-2（marin 中文聲 + 蘇菲人設）
  - 嘴 = MuseTalk v1.5（Lyra Lab/Tencent Music · MIT 授權）
- **三方計畫書**：沙利曼信任巡檢 + 女巫純黑 Duix 介面 + 卡西法 Modal 部署
- **Sally 6 歲紅線守則**：subject_guard 雙層防護（客戶端 + 服務端）
- **Modal A10G 自家後台**：≈ $66/月 嘴對齊層、scale-to-zero 不用 $0
- 整體月費 $185（聽 $46 + 說 $72 + 嘴 $66 + 健康檢查 $1）

---

## 規劃中（未上線）

### v0.7.3
- info icon 重做（有功能版 · 點開顯示版本號 + 本檔內容）
- 位置：女巫定（右上名稱旁 / Start 按鈕旁）

### v0.8
- 4 狀態動畫切換邏輯（idle / speaking / task-received / task-handoff）
- GPT realtime 自己呼叫狀態切換接口（function call）
- 待機 2 支輪播（idle-1 / idle-2 五五波隨機）
- 講話動畫事件觸發（蘇菲開始講話 → speaking loop · 講完 → 回 idle、不依賴 5 秒固定）
- 待 Edward 產出 4 支：思考 / 高興 / 崇拜 / 打哈欠

---

*版本紀錄統一從 v0.7（三層架構上線）起記 · v0.6 前為 Tavus 走錯架構版本、5/23 後不再 reference*
