# 🎙 蘇菲 gpt-realtime-2 即時中文語音 demo

> v0.2.2 ship · 2026-05-22 · 卡西法
> branch: voice-path/v2.0-breeze-poc · castle/main 零污染

---

## 一步開動

開瀏覽器（推薦 Chrome 或 Edge）打開：

**https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/**

→ 自動跳到 `/static/index.html`
→ 按琥珀色的「開始對話」按鈕
→ Chrome 問麥克風權限 → **允許**
→ 等狀態條變綠（連線完成、你講話蘇菲就會回）
→ 直接講中文。例如「蘇菲、你聽得到我嗎」「跟我聊一下今天 BeyondPath 的進度」

---

## 你會看到什麼

正常情境（gpt-realtime-2 work）：
- 狀態條變綠：「連線完成 · 你講話蘇菲就會回。」
- 黑色 log 區會顯示 `track received: audio` + `pc state: connected` + `session.update sent`
- 你講話 1-2 秒後蘇菲就會語音回。語氣應該是溫暖、簡短、台灣腔。

降級情境（OpenAI 還沒對你的 org enable gpt-realtime-2）：
- 狀態條變橘：「注意：gpt-realtime-2 不可用、自動降回 gpt-realtime」
- 但仍可正常對話。

---

## 預期體驗

| 維度 | 廠商 spec | 實際感受 |
|---|---|---|
| 端到端延遲 | 500ms - 1.5s | 跟人講話差不多自然 |
| 中文品質 | OpenAI GA 2026 最強之一 | 應該流暢、不卡 |
| Voice profile | `marin`（溫暖中性女聲、5/8 release）| 比較像友善的女特助、不會太機器 |
| 打斷支援 | server_vad turn_detection | 你開口會被偵測、但 demo 預設關了 `interrupt_response`、避免 echo loop |
| Cold start | Modal scale-to-zero | 第一次連可能 3-5 秒、之後熱機後 < 250ms |

---

## 跟原 v0.1.5 差在哪

| 項目 | v0.1.5（舊）| v0.2.2（今天 ship）|
|---|---|---|
| 模型 | gpt-4o-realtime-preview（Beta）/ gpt-realtime | **gpt-realtime-2** + 自動 fallback |
| API endpoint | `/v1/realtime/sessions` mint ephemeral token + WebSocket | **直接 /v1/realtime WebRTC**（OpenAI 5/8 GA、Beta 退役）|
| 瀏覽器接法 | 沒前端（要自己寫 WebSocket client）| `/static/index.html` 一鍵 demo + WebRTC |
| Persona 注入 | session config inline | 透過 data channel `session.update` event 推 instructions（更 GA-spec 對齊）|
| 預設 voice | marin | marin（不變）|
| 中文 transcription | gpt-4o-transcribe zh | 同（不變）|

---

## 如果壞了

### 連不到 / 504
Modal scale-to-zero、cold start。**等 10 秒重 refresh 一次**。

### 「openai_key_missing」
Modal secret `openai` 沒掛上。檢查：
```
modal secret list | grep openai
```

### 「openai_sdp_exchange_failed」 + status 400
SDP 內容有問題、可能是瀏覽器 WebRTC bug。換另一個瀏覽器（Chrome → Firefox 或反之）。

### 「openai_sdp_exchange_failed_both」
gpt-realtime-2 + gpt-realtime 都失敗。可能你 OpenAI org 還沒 access。看 detail 訊息。

### 麥克風 grant 沒跳出
1. 確認瀏覽器網址列左邊地球 icon → Permissions → Microphone → Allow
2. 重 reload

### 講話沒反應
看黑色 log。有沒有 `track received: audio`？
- 有 → audio 路通了、是 ICE / DTLS 問題（防火牆）
- 沒有 → SDP 沒 negotiate 完、看 errors

---

## 後端架構（給你參考）

```
Browser (你)
    │
    │ POST /sdp (with WebRTC SDP offer)
    ▼
Modal castle-voice-engine v0.2.2
    │  - load persona sophie.yaml (instructions, voice=marin)
    │  - mint master key from Modal secret openai
    │  - POST OpenAI /v1/realtime?model=gpt-realtime-2 with SDP
    │  - if 404 model_not_found → retry with gpt-realtime
    │
    ▼
OpenAI gpt-realtime-2 GA endpoint
    │  - SDP answer
    │  - WebRTC peer connection established direct browser ↔ OpenAI
    │  - audio in/out + data channel events
    │
    ▼
你 ↔ 蘇菲 voice-to-voice
```

---

## v0.3+（未來）

- **Function calling**：接城堡 7 subagent（霍爾 / 馬魯克 / 沙利曼 ...）讓蘇菲語音可派工
- **Voice profile 自訂**：換 alloy / coral / cedar 比較看哪個最像你心中的蘇菲
- **錄音 replay**：把對話存成檔（dogfood 用、不對外）
- **WebRTC 升 WebSocket fallback**：避免企業防火牆 block UDP/SRTP

---

## 你不必動的事

- ❌ 不必 `modal deploy`——v0.2.2 已 deploy
- ❌ 不必設 secret——`openai` Modal secret 你早上更新好了、castle-voice-engine 直接讀
- ❌ 不必 git push——voice-path/v2.0-breeze-poc branch 我 ship 完會 push（見最後 commit 紀錄）
- ❌ 不必動 castle/main——這 branch 是獨立 PoC、main 零污染

---

**ship 紀錄**：
- backend：`castle/server/realtime_endpoints.py` v0.2.0 → v0.2.2
- frontend：`castle/static/index.html`（新建、305 行、單一檔）
- app.py：v0.1.5 → v0.2.0（mount static + redirect /）
- engine_server.py：bump version 0.1.0 → 0.2.0
- Modal app：deployed 3 次（v0.2.0、v0.2.1 hotfix GA、v0.2.2 final）

**Modal URL**：https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/
**Modal dashboard**：https://modal.com/apps/edwardt0303/main/deployed/castle-voice-engine

---

*ship 完成。Edward 起床直接開瀏覽器跟蘇菲講中文。任何問題回報蘇菲、我們可以 iterate。*

— 卡西法 🔥
