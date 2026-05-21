# Breeze-ASR-25 Research（Day 2 · 卡西法 5/22）

## Model 基本資訊（待 deploy 後驗證）

| 項目 | 值 | 來源 |
|---|---|---|
| HuggingFace ID | `MediaTek-Research/Breeze-ASR-25` | 預期路徑、Day 2 deploy 後 confirm |
| 基底 | Whisper-large-v3 fine-tune | MediaTek 公告 |
| 訓練語料 | 繁中（台灣）+ 簡中 + 英 + code-switch | MediaTek 公告 |
| Token 長度限制 | 30s segment（Whisper 標準）| Whisper-large-v3 spec |
| GPU 需求 | A10G 24GB 足（fp16）| Whisper-large 約 3GB weight |
| License | Apache-2.0 | 用戶 PoC + 商用都 OK |

## 對標廠商基準

- **廠商產品中文 ASR 聽錯率**：7.97%
- **Day 2-3 目標**：跑 10 句中文 → 算 CER → 對比 7.97%
  - 若 ≤ 8%（持平）→ Breeze ASR 候選
  - 若 ≤ 5%（顯著優）→ Breeze 顯著贏、Phase 2 GO
  - 若 ≥ 15%（明顯差）→ NO-GO escalate 蘇菲

## CER（Character Error Rate）公式

```
CER = (S + D + I) / N
  S = substitutions（替代字數）
  D = deletions（漏字數）
  I = insertions（多字數）
  N = reference 總字數
```

中文 ASR 通常用 CER 而非 WER（中文「字」是基本單位、不是「詞」）。

## 10 句中文測試句設計（Edward 開錄前先審）

涵蓋類型：
- 日常對話（3 句）
- 城堡專業詞（2 句）— 蘇菲 / 卡西法 / 蕪菁頭 / BeyondPath
- 數字 + 量詞（2 句）— ASR 常錯點
- code-switch 中英混（2 句）— Voice Path 主要場景
- 情緒語氣（1 句）— 語氣強弱

### Test set v1（待 Edward 審）

```
1. 我今天早上跑了五公里、覺得體力比上個月好很多
2. 蘇菲幫我看一下 BeyondPath 昨天的留存率有沒有跌
3. 卡西法去確認 Vercel preview URL 跑得起來
4. 派蕪菁頭看用戶 cohort 的退訂原因 top 3
5. 我預算大概一個月五千塊、能不能撐三個月
6. 三點半開會、會議室在 12 樓 A 區
7. 這個 component refactor 一下、別讓 props drilling 變五層
8. CFO 拉預算的時候、記得 highlight 那個 ROI 是 3.2 倍
9. 我有點不耐煩了、能不能直接給我結論不要鋪陳
10. Sophie can you help me draft an email to Marc about Q3 strategy
```

### 評分流程

1. Edward 用手機錄 10 句（每句單獨檔、命名 `t01.m4a` 到 `t10.m4a`）
2. 卡西法跑 `/breeze/audio/preprocess` 轉 WAV
3. 卡西法跑 `/breeze/asr/transcribe`（Day 2 接好後）
4. 用上面 ground truth 算 CER
5. 對比廠商 7.97% baseline

## 評分腳本（Day 2 寫、Day 3 跑）

```python
# breeze_poc/day2/asr_score.py（pending）
import jiwer  # CER 套件、Modal image 待加

def score(ref: str, hyp: str) -> float:
    return jiwer.cer(ref, hyp)

# Test loop:
# for i in range(1, 11):
#     hyp = transcribe(f"t{i:02d}.wav")
#     ref = TEST_SET[i-1]
#     print(f"t{i:02d}: CER={score(ref, hyp)*100:.2f}%")
```

## Pending Day 2-3 dependencies

- ⏳ Edward 建 `breeze-poc-auth` Modal secret
- ⏳ Edward 審 10 句測試句（可改）+ 用手機錄 t01-t10.m4a
- ⏳ Modal image 加 jiwer 套件（next deploy 加）
- ⏳ Modal image 加 transformers Whisper auto-download cache 機制（model 大 ~3GB、首跑慢）
