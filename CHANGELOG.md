# Voice Path Changelog

> 蘇菲對外網址：https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/static/index.html
> 分支：voice-path/v0.7-musetalk-self-host

---

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
