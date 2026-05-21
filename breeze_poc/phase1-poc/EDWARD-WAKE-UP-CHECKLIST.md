# Edward 起床驗收清單（Voice Path v2.0 Phase 1 PoC · Day 3+4）

> 卡西法 2026-05-22 凌晨自治 ship
> Branch: `voice-path/v2.0-breeze-poc`
> Edward 動作：`git pull` + 讀本檔 + 聽音檔（不到 10 min）

---

## 1 分鐘 quick scan

| 檢查 | 在哪看 | 預期 |
|---|---|---|
| TTS 10 句生成 | `breeze_poc/phase1-poc/audio/t01.wav ~ t10.wav` | 10 個 WAV、檔案大小 > 5KB |
| voice clone demo | `breeze_poc/phase1-poc/audio/edward_voice_clone_demo.wav` | 1 個 WAV、用 Edward 聲音 clone 的女聲 |
| round-trip CER | `breeze_poc/phase1-poc/results/round-trip-cer.csv` | 每句 CER %、mean / median / max |
| Edward voice 聽錯率 | `breeze_poc/phase1-poc/results/edward-voice-spotcheck.md` | Edward 聲音 → ASR 文字 |
| 延遲 P50 / P95 | `breeze_poc/phase1-poc/results/latency.csv` | TTS / ASR 各 P50 P95 |
| Day 3 escalate 觸發 | `breeze_poc/phase1-poc/DAY3-COMPLETE.md` | NO-GO list 應為空 |
| 城堡派工 demo | `breeze_poc/CASTLE-DISPATCH-DEMO.md` | Claude function calling 接城堡 1 case + trace |

---

## 5 分鐘聽音檔（重點）

### A. 廠商台灣腔女聲（10 句，無 voice clone）
聽 `breeze_poc/phase1-poc/audio/t01.wav` 一聽就懂。

主觀判斷：
- 聲音自然嗎？vs Google / iOS 中文女聲。
- 台灣腔嗎？vs 中國普通話。
- 「BeyondPath / refactor / Q3」這類英文夾雜詞唸得對嗎？（看 t02 / t07 / t10）

### B. Edward voice clone demo（Phase 2 起手）
聽 `breeze_poc/phase1-poc/audio/edward_voice_clone_demo.wav`。

這是用你 4/28 錄的 `voice_samples/edward_for_eagle.m4a` 當「prompt 聲線」、要 BreezyVoice 唸一句中文。聽起來：
- 像不像你的聲音？（音色 / 語速 / 共鳴）
- 30 秒 prompt 真的能 clone 嗎？（廠商宣稱 zero-shot）
- 「值得不值得繼續走 Phase 2？」由你聽完拍板。

---

## CER 怎麼判讀

`round-trip-cer.csv` 第一行 header、之後每行 1 句。

```
tag,ref_chars,hyp_chars,cer_pct,...
t01,21,22,4.76,...
```

- **CER < 5%** = 跟廠商 7.97% 顯著贏 → Phase 2 GO 候選
- **CER 5-8%** = 跟廠商持平 → 中性 / 看其他指標
- **CER 8-15%** = 廠商勝 → 不換、留 OpenAI Realtime
- **CER > 15%** = 已 escalate（DAY3-COMPLETE.md 會標紅）

**注意**：這是 round-trip CER（TTS → ASR），同個 stack 自我對話、會比真實人聲 CER 樂觀。Edward voice spotcheck 補真實人聲的 baseline 觀感（沒 ground truth 算數字，主觀聽）。

---

## 延遲怎麼判讀

`latency.csv` 4 行：
```
category,count,p50_ms,p95_ms,min_ms,max_ms,mean_ms
tts_server_latency,10,...
asr_server_latency,11,...
```

- **TTS P95 < 3000ms** = 對話節奏 OK
- **ASR P95 < 3000ms** = 反應速度 OK
- **超過 3000ms** = DAY3-COMPLETE.md 會標紅 escalate

---

## 4 個 escalate 觸發點當前狀態

打開 `breeze_poc/phase1-poc/DAY3-COMPLETE.md` 看「NO-GO escalate triggers」段。應該寫 `All cleared - no escalate triggered`、若有任一觸發會列出來。

| # | 觸發 | 卡西法行為 |
|---|---|---|
| 1 | CER mean > 5% | 不擅自 escalate、留給 Edward 主觀判 |
| 2 | TTS P95 > 3000ms | DAY3-COMPLETE 標紅 + 給蘇菲 |
| 3 | ASR P95 > 3000ms | DAY3-COMPLETE 標紅 + 給蘇菲 |
| 4 | < 10/10 生成 / transcribe 成功 | DAY3-COMPLETE 標紅 + log root cause |

---

## Phase 2 起手 nice-to-have（看時間有沒做完）

如果這 2 個檔有出現代表 bonus 也完成、Phase 2 起手過：
- `breeze_poc/phase2-poc/eagle_enrollment_result.md` — Picovoice Eagle 聲紋註冊 + 識別準確度
- `breeze_poc/phase2-poc/wake_word_setup.md` — Picovoice 「蘇菲」中文喚醒詞訓練狀態

沒這 2 個檔 = Phase 2 起手沒做完（時間不夠）、不算失誤、Phase 1 MUST 7 個 artifact 是主目標。

---

## Edward 起床要不要動什麼？

**不需要動**。

如果 wake word 中文必須在 Picovoice Console 手動點訓練、會在 `breeze_poc/phase2-poc/wake_word_setup.md` 寫清楚步驟（1 min 點 1 下）。其他都自動。

---

## 結論：Phase 1 GO/NO-GO 拍板

Edward 起床後判斷 Phase 1 結果、決定 Phase 2 是否繼續：

- **A. Phase 2 GO**：CER 結果可接受 + 廠商台灣腔女聲 OK + voice clone demo 像你 → Phase 2 繼續做聲紋認證 + wake word
- **B. NO-GO 退**：CER 太差 / TTS 不台灣 / voice clone 像別人 → archive PoC、保留 OpenAI Realtime
- **C. 並存**：Breeze 中文、OpenAI 英文 fallback → v2.1 dual-backend

拍板回 Slack `#項目討論-agent`、卡西法收到就開 Day 4-7。

---

## 卡西法雙軌工時校準（Day 3 自治）

- **預估**：Day 3 mid-progress = 8 hr（資深工程師、AI 輔助）
- **移動城堡**：卡西法 ~4-6 hr 自治推進（含 6 個 escalate 觸發點偵測 + 4 stage 自動化 + 文檔）
- **倍率**：~0.7-0.8×（含 LLM 模型 cold start 等待時間）
