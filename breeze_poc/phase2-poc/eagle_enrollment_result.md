# Picovoice Eagle 聲紋註冊（Phase 2 起手）

> 卡西法 2026-05-22 Day 3+4 自治
> 目的：用 `voice_samples/edward_for_eagle.m4a` 註冊 Edward 聲紋、未來 wake word + voice ID 對齊
> Branch: `voice-path/v2.0-breeze-poc`

---

## 狀態（5/22 凌晨）

**未實際註冊**。Eagle SDK 註冊需 Picovoice AccessKey + 本機 SDK（Python 或 Web）+ `pveagle` pip package。

當前阻塞：
1. ⏳ Picovoice AccessKey 待 Edward 起床去 https://console.picovoice.ai 申請（個人版免費）
2. ⏳ `pip install pveagle` 在本機 Python 3.14 + Modal 都還沒測（SDK 可能要 < Python 3.12）

---

## Phase 2 起手已 ship 的東西

### 1. 註冊 stub 腳本（先前 session 已建）

檔：`breeze_poc/register_eagle_speaker.py`

預期流程（Edward 起床後 5 min 完成）：
```bash
# 1. 設 AccessKey
export PICOVOICE_ACCESS_KEY="your-key-from-console"

# 2. 跑註冊（用 voice_samples/edward_for_eagle.m4a）
py breeze_poc/register_eagle_speaker.py enroll voice_samples/edward_for_eagle.m4a

# 3. 跑驗證
py breeze_poc/register_eagle_speaker.py verify voice_samples/edward_for_eagle.m4a
```

### 2. Eagle 中文聲紋已知限制

- ✅ Eagle 是「speaker recognition」（誰在說、不是說什麼）、語言 agnostic
- ✅ 中文 / 英文 / 任何語言都能用、只要錄音 quality 夠
- ⚠ 建議 enroll audio ≥ 20s 純人聲（無背景音）
- ⚠ 不要 cross-mic（手機錄 enroll、然後用筆電 mic verify 會掉分）

### 3. Phase 2 目標誤拒率（FRR）/ 誤認率（FAR）

| Metric | Target | 測法 |
|---|---|---|
| FRR (Edward → 認成 Edward) | < 5% | 跑 50 次 verify、看 ≥ 47/50 通過 |
| FAR (他人 → 誤認 Edward) | < 1% | 跑 50 次別人聲音 verify、看 ≤ 0-1 個誤通過 |
| 適應期 | 註冊後立即 verify | 不需訓練累積 |

---

## Edward 起床 3 min 動作（若想啟動 Phase 2）

1. 去 https://console.picovoice.ai/ 申請 AccessKey（免費、Google login）
2. 把 key 貼到 `castle-voice-engine/.env`：`PICOVOICE_ACCESS_KEY=your-key`
3. 回 Slack #項目討論-agent 一句「Phase 2 GO」
4. 卡西法收到立刻：
   - `pip install pveagle` 跟 Modal image 加 pveagle
   - 跑 enroll + verify、寫 FRR / FAR 量測
   - update 本檔狀態為「已完成」

---

## 為什麼這份檔在 Day 3 就出（沒等 Edward）

Edward 5/22 凌晨拍板 Phase 2 起手 nice-to-have、但 deliverable #8 是「eagle enrollment result」。
真實情況：本機 + Modal 都沒 Picovoice AccessKey、不可能真註冊。
ship 本檔 = 把「為什麼還沒做完 + Edward 1 步起床能解」交代清楚、不假裝完成、不丟事給 Edward。

---

## 結論：Phase 2 Eagle 起手 = 架構準備好、待 1 個 AccessKey 即可開跑
