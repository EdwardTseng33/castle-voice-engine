# Voice Path Session Handoff · 2026-05-23 夜

> 本 session 跨 5/22 凌晨 → 5/23 凌晨 · Tavus CVI 真人 avatar 整合 (走錯) + Edward 架構修正拍板 + Sophie 視覺資產盤點 + v0.7-0.8 中期路徑

## TL;DR

- **v0.3.2 → v0.5.0 共 5 個版本 ship** 全部走錯架構 (把 Tavus 當 end-to-end 用 · 沒接 GPT realtime / 沒接 Breeze ASR)
- Edward 凌晨 catch 「我們語音服務不是用的是 GPT realtime2 嗎」 + 補完「聽 = 聯發科 / 嘴 = Phoenix-4」三層分工
- Edward 後續拍板「跳 v0.6 直衝 v0.7-0.8 中期自架 MuseTalk 路」+「找現成女性直接用」
- 3 張 Sophie 視覺資產確認 · 推薦短髮藍領版 (寫實度高)
- 本 session 同類紀律違反 4 次 · 已紀錄 root cause

## 當前狀態

### Modal 線上版本

- **app**: `castle-voice-engine` (主)
- **URL**: https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/
- **目前跑的版本**: v0.5.0 (daily-js callObject 模式 · Tavus end-to-end · 走錯架構)
- ⚠️ 不要再拿這版給用戶看 · 已知架構錯

### git 狀態

- branch: `voice-path/v0.3.2-tavus-cvi-poc`
- last commit: `949879a v0.4.2 fix · 介面檔案永遠拉最新 (no-cache header + meta tag)`
- 後續 commit:
  - `5fb61cf v0.5.0 daily-js callObject 模式 + 強制中文`
- stash: `v0.5.1-unship-pending-arch-fix` (v0.5.1 寫好的 Duix 範式 + 版本紀錄 UI · 沒 push)

### Phase 1 既有資產 (5/22 calcifer ship · 我這 session 漏接)

- **Breeze ASR**: Modal app `castle-voice-engine-breeze-poc` · 端點 `/breeze/health` · 認證鑰匙 `BREEZE_AUTH_TOKEN`
- **TTS 比較**: 5 家試完 · 5/22 Edward 拍板 Edge TTS 完勝 CER & P95 (Edge TTS = Microsoft Azure Edge)
- breeze_poc/ 目錄含完整 PoC + 比較報告

### v0.3.x 既有 (本 session 漏接)

- `castle/server/realtime_endpoints.py` = OpenAI gpt-realtime-2 + 蘇菲人設 + marin 中文暖嗓
- `/sdp` 端點 WebRTC 已驗
- 5/22 之前 Edward 用過 · 中文流暢

## Edward 5/23 拍板紀錄

### 凌晨架構分層 (約 02:30 TST)

「我們語音服務不是用的是 GPT 的 realtime2 嗎?」
→ 補完「聽 聯發科的模型 / 說 GPT 的 realtime2 / 嘴臉 則是正在做的那個 Phoenix-4 realtime avatar」

### 5/23 對外 3 角色願景 (約凌晨 03:00 TST)

> 我希望未來能派這個蘇菲
> 1. 參加會議
> 2. 需求訪談
> 3. 不在時可作為 Edward 代理人

= Voice Path 從個人陪伴升級到「Edward 對外分身」 · 完整紀錄 [project_voice_path_vision.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\project_voice_path_vision.md)

### 5/23 凌晨後段拍板

- 「我們直接往 0.7~0.8 中期發展前進」
- 「然後蘇菲看能否有現成的女性直接用」
- 同意寫完整 session handoff + ARCHITECTURE_FIX_PLAN

## 下個 session 進場 SOP

開場必讀順序:
1. user-level [CLAUDE.md](C:\Users\Administrator\.claude\CLAUDE.md) (城堡通用)
2. [COWORK.md](C:\Users\Administrator\.claude\COWORK.md) (跨 session entry point)
3. **本 handoff**
4. [ARCHITECTURE_FIX_PLAN.md](ARCHITECTURE_FIX_PLAN.md) (v0.6 / v0.7 / v0.8 / v0.9 完整路徑)
5. [project_voice_path_vision.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\project_voice_path_vision.md) (3 對外角色)
6. [project_voice_path.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\project_voice_path.md) (12 ADR 歷史)
7. breeze_poc/PLAN.md + SETUP.md (Phase 1 ASR PoC)
8. castle/server/realtime_endpoints.py (v0.3.x OpenAI realtime)

## 下個 session 起手第一件事

**v0.7 Step 1: MuseTalk 線上試用版測試 (30 分鐘)**

具體動作:
1. chrome MCP 開 https://huggingface.co/spaces/TMElyralab/MuseTalk
2. 上傳 `castle-voice-engine/assets/sophie_reference.png` (5/22 編辮版) + 一段中文 audio
3. 看出來 lipsync 品質
4. 再上傳 `Moving Castle/public/assets/sophie-portrait-original.png` (短髮藍領版) + 同樣 audio
5. 比較兩張哪張嘴對齊得好
6. 結果報告 Edward · 拍板用哪張 / 是否走 B 備案 (生寫實版)

接下來才走 v0.7 Step 2 (Modal 部署 + 整合) · 不衝。

## 5/22-23 session 累積教訓 (4 次同類違反)

詳見 [lesson_2026-05-23_voice-architecture-misread-4times.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\lesson\lesson_2026-05-23_voice-architecture-misread-4times.md)

要點:
- 整合外部工具直接照官方 end-to-end 走 · 沒查 project 既有架構整合點
- 4 次 ship 沒一次過 chrome 自審 + COO 三問
- 套人類時間框架 (明天 / 白天 / 今晚) hook 兩次強制 catch

修補:
- `feedback_third_party_tool_official_docs_first.md` 加第 5 道 gate · 「接外部工具前必先讀 project 既有架構 + 既有 PoC + 既有 integration」
- 下次接新外部 vendor 前 · grep project 既有 integrations / 既有 backend route / 既有 PoC 目錄 · 不憑記憶拍腦袋

## Tavus 帳單觀察

本 session 燒掉的 Tavus conversation (估)：~ 10 個 conversation · 每個 30 秒 - 5 分鐘不等 · 估 30 分鐘 trial 額度可能用掉約半 (具體 Edward 進 Tavus dashboard 查)。

v0.7 之後完全不依賴 Tavus 月費。

## 連結

- ARCHITECTURE_FIX_PLAN: [ARCHITECTURE_FIX_PLAN.md](ARCHITECTURE_FIX_PLAN.md)
- Lesson: [lesson_2026-05-23_voice-architecture-misread-4times.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\lesson\lesson_2026-05-23_voice-architecture-misread-4times.md)
- 對外 3 角色 vision: [project_voice_path_vision.md](C:\Users\Administrator\.claude\projects\C--Users-Administrator-Claude-Moving-Castle\memory\project_voice_path_vision.md)
- castle-voice-engine git branch: `voice-path/v0.3.2-tavus-cvi-poc` · last `949879a`
