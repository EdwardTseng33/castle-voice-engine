# castle-voice-engine · 真實狀態（v0.3.0 進行中）

> 取代 `session-handoff-2026-05-22-final.md`（那份過度樂觀、Phase 2 partial / Phase 3 都寫成「ship 完」實際沒進程式庫）
> 本檔在 castle-voice-engine 程式庫頂層、跨 session 蘇菲 cold start 第一個讀
> v0.3.0-2026-05-22 PM · 蘇菲重寫 · Edward「一路推到 P3 我看結果」拍板

---

## 📋 Phase 狀態（事實 only · 全部對得起 git log）

| Phase | 狀態 | 證據 |
|---|---|---|
| **Phase 1 · gpt-realtime-2 PoC** | ✅ ship | commit `63a744e` v0.2.3 hotfix · Modal live · branch `voice-path/v0.2.3-ga-calls-hotfix` |
| **Phase 2 前置（Eagle / Porcupine 探索）** | ✅ ship | breeze_poc/phase2-poc/ · register_eagle_speaker.py · wake_word_setup.md（卡西法 5/22 Day 3-4 自治） |
| **Phase 2 後半段骨架（蘇菲手寫）** | ✅ ship | branch `voice-path/v0.3.0-phase3-camera` · 12 個新檔（castle/dispatch/ + castle/integrations/ + dispatch_endpoints.py + EDWARD-PICOVOICE-2-STEPS.md） |
| **Phase 2 後半段啟用** | ⏸ 卡 Edward 3 件物理動作 | 5-7 分鐘可動完、見 EDWARD-PICOVOICE-2-STEPS.md |
| **Phase 3 鏡頭多模態 build** | 🔄 卡西法跑中 | branch 同上 · castle/multimodal/ 已開始建（agent background）|
| **桌面情境感知（pywin32）** | ⏸ Edward 待拍板 | A · Phase 3.5 延後（蘇菲推薦）/ B · 拉進 Phase 3 |

---

## 🔗 對外 URL（live）

| 用途 | URL |
|---|---|
| **Phase 1 demo（gpt-realtime-2 即時對話）** | https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/ |
| **Modal dashboard** | https://modal.com/apps/edwardt0303/main/deployed/castle-voice-engine |
| **GitHub repo** | https://github.com/EdwardTseng33/castle-voice-engine |
| **當前 active branch** | `voice-path/v0.3.0-phase3-camera`（含 Phase 2 後半段 + Phase 3 in-progress）|

---

## 🚨 Edward 待動 / 待拍板

### 3 件 5-7 分鐘物理動作（Phase 2 後半段 unblock · 我做不了、要你動）

| # | 事 | 時間 | 怎麼動 |
|---|---|---|---|
| 1 | 申請 Picovoice AccessKey | 2 min | https://console.picovoice.ai/ Google login → copy key → 給我或自己貼 `.env` |
| 2 | 訓練「蘇菲」中文喚醒詞 | 3-4 min | 同 console → Porcupine → Train Custom → 下載 sophie_zh.ppn |
| 3 | 下載 spaCy 中文模型 | 1 min | 我可以幫你跑 `python -m spacy download zh_core_web_sm`、跟我講一聲 |

完整教學在 `EDWARD-PICOVOICE-2-STEPS.md`。

### 1 件拍板（Phase 3 scope）

桌面情境感知（pywin32 抓 app 名）= Phase 3 必做 vs Phase 3.5 延後？

- 蘇菲推薦 Phase 3.5 延後（比鏡頭更敏感的個資高密度區、跟北極星即時對話無直接相關）
- 你拍板我就改 ADR-018 + Phase 3 範圍

---

## 🌸 Phase 2 後半段骨架 · 我這 turn 做了什麼

### castle/dispatch/ · 城堡 7 同事 function calling

5 個檔：
- `castle_members.py` — 7 人定義 + capabilities + when_to_dispatch（howl/calcifer/witch/turnip/markl/sophie/suliman）
- `tools_schema.py` — OpenAI Realtime tools 2 個（`dispatch_to_castle_member` + `recall_recent_dispatches`）
- `task_log.py` — jsonl 跨 session 派工紀錄（events/dispatch/YYYY-MM-DD.jsonl · 已 .gitignore 防漏）
- `dispatch_handler.py` — Claude Haiku 模擬城堡同事角色（PoC stub · 未來接 Hub task queue）
- `__init__.py` — 公開 API

### castle/integrations/ · 本機跑配件

3 個檔：
- `picovoice.py` — Porcupine 喚醒詞 + Eagle 聲紋骨架（Edward 給 AccessKey + .ppn 就接、SDK lazy import 沒裝也不炸）
- `spacy_ner.py` — 中文 NER 個資過濾（regex pass + spaCy PERSON entity · email/phone TW/身分證/信用卡都 catch）
- `__init__.py` — 公開 API

### castle/server/ 改動

- `dispatch_endpoints.py`（新）— 4 個路由：`GET /dispatch/tools` + `POST /dispatch` + `GET /dispatch/recent` + `GET /phase2/status`
- `realtime_endpoints.py`（改）— SDP exchange response header 加 `x-realtime-tools-b64`（browser 從 header 拿 tools schema、用 data channel session.update 注入 OpenAI session）

### castle/personas/sophie.yaml 改動

加 dispatch awareness 段：Sophie 知道有 2 個工具、何時用、≤ 25 字硬規不破。

### EDWARD-PICOVOICE-2-STEPS.md（新）

5-7 分鐘 3 件物理動作教學（上一版 handoff 寫了這檔但實際不存在、現在補回）。

### Smoke test 結果

本機跑 9 個 import + API 測試全過：
- 7 castle members 對齊 user-level CLAUDE.md
- 2 tools schema build OK
- dispatch_function_call no-API-key path 跑 OK（stub mode）
- recall_recent_dispatches 立刻能查回 events
- PII regex catch email + phone TW
- Picovoice / spaCy status detection 正確

---

## 🔥 Phase 3 鏡頭多模態 · 卡西法跑中

派工 SOW 完整寫死、agent ID `a7b4443a10d09dd72`、5 個 deliverable：

1. MediaPipe 鏡頭接入（`castle/multimodal/camera.py`）
2. FaceMesh + Pose + Hands 模型整合
3. 看畫面 + Claude vision 分析 + 即時 narrate
4. 隱私守則 7 大類落到 code（對應 security-architecture-checklist.md）
5. FastAPI 整合 + `/camera/enable` `/camera/disable` `/camera/kill` `/camera/status` endpoints + browser preview button

不在範圍：桌面情境感知 pywin32（Edward 待拍板）+ production hardening + voice clone 替換。

預估真實工時 4-6 hr。ship 完通知格式 `[CALCIFER-PHASE-3-DONE]`、我整合 + 更新本檔 + 跟 Edward 報結果。

---

## ⚠ 上 session handoff 跟實況落差（事實 catch）

`session-handoff-2026-05-22-final.md` 寫的跟實際 git log 對不上：

| handoff 寫 | 實況 |
|---|---|
| 「castle-voice-engine v0.3.0 Phase 2 partial（commit 6dfd25e 系列）」 | 6dfd25e 實為 `breeze_poc Chatterbox correction`、不是 v0.3.0 Phase 2 |
| 「branch `voice-path/v0.3.0-phase2-partial-from-v0.2.2`」 | 不存在（本地 + 遠端都查不到） |
| 「Phase 2 partial = 接城堡 7 同事 + spaCy + STT Web UI」 | 程式庫沒這份 ship · 本次 turn 蘇菲重寫補 |
| 「EDWARD-PICOVOICE-2-STEPS.md 教學 ready」 | 檔不存在 · 本次 turn 重寫補 |
| 「卡西法 Phase 3 鏡頭 build · agent a79640032e9a9baf0 · background 跑中」 | 上 session 跑掉沒 ship · 本次 turn 重派 agent `a7b4443a10d09dd72` |
| 「沙利曼 35 條 ship 前 checkpoint」 | 文件不存在 · 改用 `security-architecture-checklist.md` 7 大類 + ADR-018 3 項實測為基底 |

可能 root cause：上 session 蘇菲跨日 24 小時 + 6 次違反、寫 handoff 時把「派出去 background 跑」當成「已 ship」、agent session 結束 = work 跟著掉、沒上傳。

本次 turn 紀律：
- ✅ 卡西法派工 foreground reading + agent background 啟動 + 我這 turn 寫 STATUS 反映真實
- ✅ Phase 2 骨架蘇菲手寫不依賴 agent、smoke test 過才 commit
- ✅ branch push 完成、可從 GitHub verify
- ⏸ Phase 3 等卡西法完成通知再 ship

---

## 📊 Task tracker（本 session）

| # | 狀態 | 內容 |
|---|---|---|
| 1 | ✅ completed | Phase 2 後半段：Picovoice 整合骨架（蘇菲手寫） |
| 2 | 🔄 in_progress | Phase 3 鏡頭多模態 build（卡西法 background） |
| 3 | ✅ completed | 查 Phase 2 v0.3.0 partial 失蹤進度（結論：handoff 過度樂觀、不存在）|
| 4 | 🔄 in_progress | 更新真實狀態的 STATUS.md（本檔正在寫） |

---

## 🚀 下個動作

按優先序：

1. **等卡西法 Phase 3 通知**（agent background、我會收到 task complete notification）
2. **整合 Phase 2 + Phase 3**：calcifer ship 後合併 app.py mount + static/index.html function_call handler + requirements.txt
3. **Modal deploy 整合版本**：v0.3.0 ship
4. **重寫 session-handoff 給下個 session 蘇菲**

Edward 想動的話、3 件物理動作隨時可動、不卡 Phase 3。

---

*v0.3.0 ship-progress · 2026-05-22 PM · 蘇菲手寫 · 取代 session-handoff-2026-05-22-final.md*
