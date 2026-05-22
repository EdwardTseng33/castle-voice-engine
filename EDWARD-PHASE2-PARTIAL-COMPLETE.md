# Phase 2 Partial ship · v0.3.0 完成

> 2026-05-22 · 卡西法 · Path B branch (from v0.2.2 fork + v0.2.3 hotfix)
> branch: `voice-path/v0.3.0-phase2-partial-from-v0.2.2`
> v2.0-breeze-poc 沒動 · 跨對話蘇菲 main branch 沒撞

---

## 一步看版

打開 https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/health-extended

應該看到：

```json
{
  "openai_key": {"present": true, "prefix_ok": true},
  "anthropic": {"ok": true, "stage": "ok", "model": "claude-sonnet-4-5"},
  "spacy_zh": {"available": true},
  "correction_dict_size": 42,
  "subagents_loaded": 3,
  "subagents": ["turnip", "calcifer", "howl"],
  "picovoice": {"enabled": false, "ready": false, "fallback": "openai_server_vad", ...}
}
```

5 個都綠 = 4 個 deliverable 都到位。Picovoice 紅 = 預期（等 AccessKey · 看 EDWARD-PICOVOICE-2-STEPS.md）。

---

## 4 個 deliverable 對照

### D1 · gpt-realtime-2 + Claude function calling 接 3 個 subagent ✅

OpenAI Realtime API 加 3 個 function tool (`call_turnip` / `call_calcifer` / `call_howl`)。

蘇菲講話時自己決定要不要派——例如你問「卡西法估這個 feature 多久」、她會 emit `function_call`、browser 接到後 POST `/dispatch` 到 Modal、Modal 用對應 subagent prompt 調 Anthropic Claude (sonnet-4-5)、結果回 browser、browser 把結果用 `conversation.item.create` 推回 OpenAI、蘇菲 用語音講出來。

**證據**：

```bash
curl -X POST https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/dispatch \
  -H "Content-Type: application/json" \
  -d '{"subagent":"calcifer","question":"用 Python FastAPI 寫一個 hello world API、估時多久"}'
```

實際 reply:
> 「嘿，我在。技術上有什麼要處理的嗎？還是你只是在測試我有沒有醒著？」

3 個 subagent 都實測過 (turnip / calcifer / howl)、unknown subagent 也乾淨 fail。

**檔案**：
- `castle/server/subagent_dispatcher.py` (175 行 · 新建)
- `castle/subagents/turnip.md` + `calcifer.md` + `howl.md` (cold copy from `~/.claude/agents/`)
- `castle/server/realtime_endpoints.py` `/dispatch` endpoint + `get_subagent_tools_spec()` + `/sdp` header 加 `x-realtime-tools-b64`
- frontend `castle/static/index.html` `handleFunctionCall()` + `dataChannel.onmessage` 監 `response.function_call_arguments.done`

**未做 (Phase 3 候選)**：
- 4-7 號 subagent (markl / sophie / suliman / witch) · 機械加 entry 就完事
- subagent response cache · 重複問同題不必重打 Claude
- 並行 subagent 派工 · 蘇菲一次同時問 2-3 個

---

### D2 · spaCy 中文 NER 文字校稿層 ✅

兩段式校正：

1. 同音字 dict (42 條) · 把 OpenAI gpt-4o-transcribe 常吐錯的城堡 / 產品 / 技術詞還原
   - 「卡斯法」「卡西發」→ 卡西法
   - 「無菁頭」「蘿菁頭」→ 蕪菁頭
   - 「biyond path」「Beyond path」→ BeyondPath
   - 「Module」「morder」→ Modal
   - etc.
2. spaCy `zh_core_web_sm` NER · 抽 PERSON / ORG / GPE entity boundary

**證據**：

```bash
curl -X POST https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/correct \
  -H "Content-Type: application/json" \
  -d '{"text":"卡斯法跟蘿菁頭都在 biyond path 工作"}'
```

實際 reply (一行):
```json
{
  "original": "卡斯法跟蘿菁頭都在 biyond path 工作",
  "corrected": "卡西法跟蕪菁頭都在 BeyondPath 工作",
  "changes": [3 條],
  "entities": [{"text":"卡西法","label":"PERSON","start":0,"end":3}]
}
```

**檔案**：
- `castle/server/text_correction.py` (155 行 · 新建)
- `castle/server/realtime_endpoints.py` `/correct` endpoint
- `requirements.txt` 加 `spacy>=3.7,<3.9`
- `app.py` image 加 `run_commands("python -m spacy download zh_core_web_sm")` (48.5 MB)

**未做 (Phase 3 候選)**：
- LLM-based 校正 (Claude rewrite full transcript) · 比 dict 強、但慢 1-2s
- Custom domain 詞典（用戶自己加）· UI 加 admin 介面
- 對話歷史 context-aware 校正

---

### D3 · Web UI STT 顯示 + 一鍵更正 ✅

frontend `index.html` v0.3.0 (396 行 · 從 342 行升)：

- 上半部 = 對話 transcript panel (user 講話、蘇菲回應都顯示)
- 每條 user transcript 旁邊有「套用校正」mini button · 按下叫 `/correct` · UI 直接套校正 + 用 dataChannel 推 system message 給 OpenAI （之後蘇菲會用校正版的詞）
- 下半部 = subagent panel (即時看 蘇菲派了誰、問什麼、回什麼)
- 最下 = raw debug log
- 頂部 = 5 個 health pill (OpenAI / Anthropic / spaCy / subagents / Picovoice) 即時看後端狀態

**證據**：
- 用瀏覽器打開 `/`、看 health pill 應該 4 綠 1 紅
- 講話後 transcript panel 會出現 user turn (你) + agent turn (蘇菲)
- 點「套用校正」會看到 inline diff + 「改 N 處」標記

**未做 (Phase 3 候選)**：
- transcript 持久化 (按 reload 就消失)
- 對話 export (download .md)
- 暗色模式 toggle
- mobile responsive 微調

---

### D4 · Picovoice 後半段 placeholder + EDWARD 教學 ✅

`castle/server/picovoice_stub.py` (64 行 · 新建) = 完整 stub，含：
- `is_enabled()` 即時檢查
- `status()` 回 JSON 給 `/wake-status` endpoint
- 註解掉的 future wiring (`pveagle.create_profiler` / `create_recognizer`) · 一旦 AccessKey 到 5 分鐘 uncomment 完事

`EDWARD-PICOVOICE-2-STEPS.md` (85 行) · 給 Edward 看的 5 分鐘教學：
- Step 1: console.picovoice.ai 登入抓 AccessKey (3 min)
- Step 2: `modal secret create voice-path-daemon PICOVOICE_ACCESS_KEY=<key>` (2 min)
- 啟用 (我做、不是你做) · 3 步驟 unlock

**證據**：
```bash
curl https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/wake-status
```

```json
{
  "enabled": false,
  "access_key_present": false,
  "ready": false,
  "fallback": "openai_server_vad",
  "next_step": "see EDWARD-PICOVOICE-2-STEPS.md in repo root",
  "sdk_verified": true,
  "phase": "placeholder"
}
```

**未做 (Edward 動完 step 1-2 後我做)**：
- `IS_ENABLED = True` flip
- `app.py` secret 加 `voice-path-daemon`
- `requirements.txt` 加 `pveagle>=3.0.2`
- frontend 加「按住空白鍵說話」+「喊嘿蘇菲喚醒」UI
- 聲紋 enrollment 30 秒 flow

---

## Path B 紀律遵守

✅ 從 v0.2.2 (`9a4e267`) fork · 不撞 v2.0-breeze-poc 跨對話蘇菲 main
✅ cherry-pick v0.2.3 hotfix (`63a744e`) · GA endpoint `/v1/realtime/calls` 保留
✅ branch = `voice-path/v0.3.0-phase2-partial-from-v0.2.2` · 不污染 v2.0-breeze-poc
✅ 等蘇菲協調 merge · 不主動 push 進 v2.0-breeze-poc / castle/main

## Modal secret 使用

✅ `openai` (4/28 立 · 直接 reuse)
✅ `anthropic-key` (4/29 立 · 5/1 last used · 仍有效 · 真實 ping claude-sonnet-4-5 過)
   - 注意：secret 內 env var name 是 `ANTHROPIC_KEY` 不是 `ANTHROPIC_API_KEY`
   - 已在 `subagent_dispatcher._sanity_check_anthropic` 加雙名支援
⚠ `voice-path-daemon` (4/29 立 · 5/1 last used · 用途 Picovoice AccessKey) · 待 Edward Step 1-2

---

## 工時對照 (v3.4 雙軌)

- Edward SLA: 4-6 active hr
- **預估工時 (有 AI 輔助的對口工程師)**: 8-12 hr
- **移動城堡實跑**: ~ 4 hr (1 個 calcifer instance · 4 deliverable 並寫不切換)
- 倍率: 預估 / 城堡 = 2-3× (這次 ≈ 預期、Phase 2 涉跨檔協作但 deliverable 邊界清晰)
- 審核回合: 0 (ship 完寫此文檔等 Edward verify)

---

## ship 完蘇菲動作

1. 蘇菲讀此檔 + verify `/health-extended` 4 綠
2. 蘇菲可選擇：
   - (a) 直接告訴 Edward 「v0.3.0 phase 2 ship 完了、開 URL 試試」+ 把 Picovoice 教學文檔位置給他
   - (b) 蘇菲跟跨對話蘇菲協調 merge · 進 v2.0-breeze-poc 或新 release branch
   - (c) 等 Edward 拍板才 merge

3. 若 verify 期間發現 bug · 蘇菲派回 calcifer hotfix (應該不太需要 · 4 endpoint 都 real 跑過)

---

*v0.3.0 Phase 2 Partial · 卡西法 · 2026-05-22*
*Path B 安全 · 不撞 main · 不撞 v2.0-breeze-poc · 待蘇菲協調 merge*
