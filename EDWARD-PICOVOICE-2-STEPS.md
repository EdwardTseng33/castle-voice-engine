# 🎙 Edward · Picovoice 動 2 件事 + spaCy 1 行（Phase 2 後半段 unblock）

> 5/22 ship 後重寫 · 兩件 picovoice console 動作 + 1 個 spaCy 下載
> 跑完三件、Sophie 就能：1) 喊「蘇菲」喚醒 2) 認你的聲音 3) 自動遮蔽 PII
> 預計花你 5-7 分鐘 · 全部都是 Google login + 點按鈕、沒有打字

---

## 為什麼是你做、不是蘇菲做

| 動作 | 我能跑嗎 | 為什麼 |
|---|---|---|
| Picovoice console 註冊 + 申請 AccessKey | ❌ | 是你的 Google 帳號 · 我不該替你註冊第 3 方 SaaS |
| Console 訓練「蘇菲」中文喚醒詞 | ❌ | Picovoice 不開放 API 自動訓練（line console 限制）|
| 跑 `pip install` + `spacy download` | ✅ | 我這 turn 完會直接幫你跑、你不用動 |
| 把 AccessKey 貼進 .env | ✅ | 你貼一行進 console、我用 Bash 寫進 .env 也可、看你 |

---

## Step 1 · Picovoice AccessKey（2 分鐘）

1. 開 https://console.picovoice.ai/
2. 點右上 `Sign in` → Google login（用 edwardt0303@gmail.com）
3. 進主控台後、左上有個 **AccessKey** 區塊、點 `Copy`
4. 回來把那串貼給我（在 Slack `#項目討論-agent` 或這個對話）、我幫你寫進 `castle-voice-engine/.env`

   或者你自己貼：在 `castle-voice-engine/.env` 加一行：
   ```
   PICOVOICE_ACCESS_KEY=<你 copy 的那串>
   ```

✅ Step 1 完成標準：`.env` 裡有 `PICOVOICE_ACCESS_KEY=...` 那行

---

## Step 2 · 訓練「蘇菲」中文喚醒詞（3-4 分鐘）

1. 在同一個 Picovoice console、左邊選單點 **Porcupine** → **Train Custom Wake Word**
2. **Language** 下拉 → 選 **Mandarin Chinese (zh)**
3. **Wake Word** 欄輸入：`蘇菲`
   - 注音：ㄙㄨ ㄈㄟ
4. **Platform** 勾 3 個全選：
   - ✅ Linux
   - ✅ macOS
   - ✅ **Windows**（你跑的就是 Windows）
5. 按 `Train` → 雲端跑 ~1 分鐘 → 彈出 download
6. 下載 3 個 `.ppn` 檔（每個平台一個）
7. 把 Windows 那個（檔名類似 `蘇菲_zh_windows_v3_0_0.ppn`）改名成 `sophie_zh.ppn`
8. 放進 `C:\Users\Administrator\Claude\castle-voice-engine\breeze_poc\phase2-poc\wake_words\`
   - 資料夾如果沒有就建一個
9. 回 Slack 跟我講「蘇菲 .ppn 放好了」、或這個對話告訴我都行

✅ Step 2 完成標準：那個 path 底下有 `sophie_zh.ppn` 檔案

---

## Step 3 · 下載 spaCy 中文模型（1 分鐘、我跑就行）

這步本來該我做、但卡 `pip install` 在你機器上、所以告訴你怎麼跑（或讓我用 Bash 跑）：

```bash
cd C:\Users\Administrator\Claude\castle-voice-engine
python -m pip install spacy
python -m spacy download zh_core_web_sm
```

或直接告訴我「跑 spaCy download」、我用 Bash 替你跑。

✅ Step 3 完成標準：跑 `python -c "import spacy; spacy.load('zh_core_web_sm')"` 沒報錯

---

## 全部 3 件做完後 · 馬上能用什麼

| 功能 | 怎麼測 |
|---|---|
| 🌸「蘇菲」喚醒 | 在瀏覽器 demo 對麥克風喊「蘇菲」、log 區會印 `[WAKE]` |
| 🔐 認你的聲音 | 你跟別人輪流講話、log 印 `[VOICE_OK]` 或 `[VOICE_UNKNOWN]` |
| 🛡 自動 PII 遮罩 | 試講你的 email / 電話 / 身分證、partial_transcript 會顯示 `[REDACTED]` |

---

## 預先註冊聲紋（Step 2 跑完才需要）

`breeze_poc/register_eagle_speaker.py` 已經寫好（卡西法 5/22 Day 3-4 ship）。AccessKey 進 .env 後跑：

```bash
cd C:\Users\Administrator\Claude\castle-voice-engine
python breeze_poc/register_eagle_speaker.py enroll voice_samples/edward_for_eagle.m4a
python breeze_poc/register_eagle_speaker.py verify voice_samples/edward_for_eagle.m4a
```

聲紋 .bin 會存到 `breeze_poc/phase2-poc/edward_eagle_profile.bin`（這個 path 跟整合骨架對齊、不用改設定）。

---

## 替代方案（如果你不想用 Picovoice）

| 想跳過 | 怎麼辦 |
|---|---|
| 「我先不弄喚醒詞」 | 跳 Step 2、Sophie 就會一直 listen、不必喊就接話（耗算力多一些）|
| 「我先不認聲紋」 | 不跑 register 那段、Sophie 不會分你跟別人的聲音 |
| 「我整個 Picovoice 都不想動」 | 跳 Step 1+2、PII 遮罩（Step 3）仍可單獨運作 |

Phase 2 後半段裡每件功能都獨立、跳哪件不影響其他兩件。

---

## 我這邊已經 ship 的程式碼（你不必動）

- `castle/dispatch/` · 城堡 7 同事 function calling 派工（語音講「派霍爾」/ 「卡西法怎麼看」就會真派）
- `castle/integrations/picovoice.py` · Porcupine + Eagle 整合骨架（你的 AccessKey + .ppn 就接上）
- `castle/integrations/spacy_ner.py` · 中文 NER 個資過濾骨架
- `castle/server/dispatch_endpoints.py` · `/dispatch` `/dispatch/tools` `/dispatch/recent` 三個接口

下一步（我會做）：
- 把 dispatch tools 寫到 OpenAI Realtime session.update（讓 Sophie 真認得這些工具）
- 加 status endpoint 讓你能用瀏覽器看「3 件物理動作做完沒」

---

*v2.0 · 2026-05-22（重寫上一版 handoff 寫的、那份檔不存在）· 三件物理動作 5-7 分鐘可動完*
