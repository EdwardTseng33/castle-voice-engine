# Picovoice Porcupine 「蘇菲」中文喚醒詞（Phase 2 起手）

> 卡西法 2026-05-22 Day 3+4 自治
> 目的：訓練「蘇菲」當 wake word、Edward 喊「蘇菲」就喚醒整個 voice loop
> Branch: `voice-path/v2.0-breeze-poc`

---

## 狀態（5/22 凌晨）

**未訓練**。Porcupine 中文 wake word 必須在 Picovoice Console 線上訓練（不能本機跑）。

當前阻塞：
1. ⏳ Picovoice AccessKey（跟 Eagle 同把、見 eagle_enrollment_result.md）
2. ⏳ Console 訓練「蘇菲」需 Edward 手動點 1 次（不能 API 自動化、Picovoice 限制）

---

## Edward 起床 5 min 動作（若想完成中文 wake word）

### Step 1：開 Picovoice Console 訓練（3 min）
1. 去 https://console.picovoice.ai/ppn → 「Train Custom Wake Word」
2. Language 選 **Mandarin Chinese (zh)**
3. Wake Word 欄輸入：**蘇菲** （注音 ㄙㄨ ㄈㄟ）
4. Platform 選 **Linux** + **macOS** + **Windows**（全勾）
5. 點 Train（雲端跑 ~1 min）
6. 下載 `.ppn` 檔（每平台 1 個）

### Step 2：放到 castle-voice-engine
1. 把下載的 `蘇菲_zh_windows_v3_0_0.ppn`（或對應檔名）放進
   `castle-voice-engine/breeze_poc/phase2-poc/wake_words/`
2. 回 Slack #項目討論-agent「wake word ready」
3. 卡西法收到立刻接 Porcupine SDK + 寫測試（Edward 講「蘇菲」→ trigger / 不講 → silent）

### Step 3：測試（5 min）
跑 `py breeze_poc/phase2-poc/wake_word_test.py`、對麥克風講「蘇菲」、看 console 是否 print `[WAKE]`。

---

## 預期實作（卡西法 Day 5-7 補）

```python
import pvporcupine

porcupine = pvporcupine.create(
    access_key="ACCESS_KEY",
    keyword_paths=["phase2-poc/wake_words/蘇菲_zh_windows_v3_0_0.ppn"],
    model_path="phase2-poc/wake_words/porcupine_params_zh.pv",  # 中文模型
)

# 連麥克風或從音檔讀 frame
# 每 frame 跑 porcupine.process(audio_frame)
# 返回 >= 0 表 wake word detected
```

---

## 為什麼這份檔在 Day 3 就出

Edward 5/22 凌晨 nice-to-have 列出 wake word setup 文件。真實狀況：
- 訓練本身要 Edward 操作 Console（無法 agent 代勞、Picovoice 規則）
- 卡西法把「Edward 起床 5 min 點 1 下」步驟先寫好、Edward 起床看本檔即知步驟
- 不擅自申請 AccessKey、不裝 SDK 等到 Phase 2 GO 才動

---

## 替代方案（若 Edward 不想用 Picovoice）

| 方案 | 中文支援 | 隱私 | 成本 |
|---|---|---|---|
| **Picovoice Porcupine** | ✅ Console 訓練 | ✅ 本機推論 | 個人免費 / 商用 $499/月+ |
| **OpenWakeWord（開源）** | ⚠ 英文為主、中文要自訓 | ✅ 完全本機 | $0 |
| **VAD 全程 listen** | N/A | ⚠ 一直錄 | Modal A10G $$ |
| **手動按鍵觸發** | N/A | ✅ 最隱私 | $0 |

PoC 階段 Porcupine 個人版免費、商用前再換。

---

## 結論：Wake word 起手 = 文件寫好、Edward 5 min 點 1 下即完成
