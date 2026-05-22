# Picovoice wake-word 2 步啟用教學

> v0.3.0 Phase 2 Path B · 卡西法 · 2026-05-22
> 本檔給 Edward 看、不必工程師、5 分鐘搞定

---

## 為什麼

v0.3.0 主路 = OpenAI server_vad (Voice Activity Detection)。網頁聽你開口、自動斷句。可用但有 4 個限制：

1. **不分人**: 你跟旁邊的人講話它都當輸入
2. **吵環境誤觸**: 咖啡店 / 開車 / 小孩在旁邊都會打斷蘇菲
3. **無 wake-word**: 不能用「嘿蘇菲」喚醒、只能按按鈕進語音模式
4. **沒個人化**: 不認識你的聲紋

Picovoice (pveagle SDK) 補這 4 個 = **on-device** 聲紋 + wake-word + speaker recognition、不上雲、隱私安全、breeze_poc Day 4 Stage 3 已驗 SDK 可裝、free tier 給你 3 個 user enrollment。

只缺一個 AccessKey 是申請類動作、不能 agent 代簽。所以分兩步、你 5 分鐘搞定。

---

## Step 1: 申請 AccessKey (3 分鐘)

1. 打開 https://console.picovoice.ai
2. 用 Google 登入 (右上角)
3. 登入後首頁就會看到「AccessKey」一串 (約 80 chars、開頭通常是 4 個字母 + 大量 base64)
4. **複製整串** (不要漏字)

>  Free tier 限制: 3 個 user enrollment / unlimited use。我們 demo 期間絕對夠。

---

## Step 2: 存進 Modal secret (2 分鐘)

打開 cmd 或 PowerShell、cd 到 castle-voice-engine 目錄、跑:

```cmd
cd C:\Users\Administrator\castle-voice-engine
modal secret create voice-path-daemon PICOVOICE_ACCESS_KEY=<貼上你複製的 80 chars>
```

(若 `voice-path-daemon` secret 已存在會跳已存在錯誤、改用 `modal secret update voice-path-daemon PICOVOICE_ACCESS_KEY=...` 或砍掉重建: `modal secret delete voice-path-daemon` 再 create)

驗證:

```cmd
modal secret list
```

應該看到 `voice-path-daemon` 在列表 (2026-04-29 立、最新 update 是你剛剛跑的時間)。

---

## 啟用 (我做、不是你做)

當 AccessKey 存在後、做以下 3 件事 (一次性):

1. 改 `castle/server/picovoice_stub.py`: `IS_ENABLED = True`
2. 改 `app.py` `secrets=[...]` 加 `modal.Secret.from_name("voice-path-daemon")`
3. `requirements.txt` 加 `pveagle>=3.0.2,<4.0`
4. `modal deploy app.py` 推上去
5. 開瀏覽器 `/wake-status` 應該回 `ready: true`

之後 v0.4 spec 會把 wake-word 接進 browser frontend (按住空白鍵 / 喊「嘿蘇菲」二選一)、enroll 你的聲紋 30 秒、之後就只認你的聲音、別人講話不會打斷。

---

## FAQ

**Q: 不申請 AccessKey 會怎樣?**
A: 一切照舊跑。Phase 2 主路是 OpenAI server_vad、Picovoice 是補強層、沒它也能 demo。只是上面 4 個限制存在。

**Q: 申請後我會被 Picovoice 開帳單嗎?**
A: Free tier 不會。3 user / unlimited use 是真的免費、不必填信用卡。商業用才要升級。

**Q: 為什麼是 pveagle 不是其他?**
A: pveagle = speaker recognition (聲紋) + wake-word 在同一個 SDK。其他選: Porcupine 只有 wake-word、Cobra 只有 VAD、Octopus 是離線 STT。pveagle 覆蓋 broad、breeze_poc Day 4 Stage 3 已驗可 install。

**Q: 我什麼時候該動?**
A: 不急。Phase 2 主功能 (語音對話 + 派 subagent + 校稿) 不依賴 Picovoice、你先用著看看夠不夠。哪天覺得「咖啡店蘇菲老被打斷」「想喊嘿蘇菲叫醒她」就動 Step 1-2、5 分鐘的事。

---

*卡西法 · v0.3.0 Phase 2 Path B · 2026-05-22*
