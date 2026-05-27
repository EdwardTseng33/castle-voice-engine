# Viseme Lipsync PoC · 規劃 + 素材規格

> Branch: `viseme-poc-v0.1`
> 啟動: 2026-05-27 · Edward 5/27 拍板「以 Duix 為標竿、走業界輕量路線」
> 不影響主線 (`v0.10/phase2-livekit-integration`) prod 部署

---

## 為什麼走 viseme 路線

之前嘗試:
- MuseTalk 即時 lipsync · 5 次失敗 (RTF 3.2 on A10G、要 A100/H100 才即時)
- A100/H100 月費 NT$3,000-200,000 · 爆 Edward 預算 100 倍

Edward 5/27 catch: **「Duix 不可能用 A100 服務每個用戶、一定有輕量解」**

業界真實做法 = **音節 → 嘴形貼圖**:
- 預烤 6-12 個嘴形
- 聽到音 → 對照表選嘴形 → 0.01 秒切換
- CPU 即可、不靠 GPU
- 跟 Duix / Tavus / HeyGen 同款技術

---

## 中文 Viseme 對照表 (簡化版 8 形)

| Viseme ID | 嘴形 | 對應中文 | 素材檔名 |
|---|---|---|---|
| **V0** | **閉嘴** (rest) | m, b, p, n, ng + 停頓 | sophie-viseme-rest.mp4 |
| **V1** | **微開** | i, y (衣 / 雨) | sophie-viseme-i.mp4 |
| **V2** | **半張** (扁) | e, ei (鵝 / 黑) | sophie-viseme-e.mp4 |
| **V3** | **大開** | a, ai, ao (啊 / 愛 / 好) | sophie-viseme-a.mp4 |
| **V4** | **圓嘴** | o, ou (哦 / 喔) | sophie-viseme-o.mp4 |
| **V5** | **撅嘴** | u, ü (烏 / 魚) | sophie-viseme-u.mp4 |
| **V6** | **咬唇** | f, w (夫 / 我) | sophie-viseme-f.mp4 |
| **V7** | **微笑** (talking idle) | 短停頓間隔 | sophie-viseme-smile.mp4 |

**為什麼 8 形夠**: 中文 60 個音節 × 嘴形組合 = 但人類視覺只能分辨 ~8 種嘴形差異 (Disney 動畫業界共識)。再多會「沒差別感」。

---

## 素材規格 (Edward 用 vivago / runway 產)

### 基本規格 (跟現有 idle / speaking 一致)
- **解析度**: 1080 × 1916 (9:16 直式)
- **幀率**: 24 fps
- **時長**: 每個 viseme **0.3 秒** (= 約 7-8 frames、用來貼上 sophie 臉)
- **編碼**: H.264 MP4
- **首尾幀**: 嘴形稍稍從 rest 過渡進去、停留中段、再過渡回 rest
  - 例: V3 (大開) = 0.1 秒過渡進大開 + 0.1 秒停留大開 + 0.1 秒過渡回 rest

### 重要紀律
1. **臉 / 頭 / 髮型 / 衣服 / 背景全部跟現有 idle.mp4 完全一致** (只嘴變)
2. **眼睛、眉毛、頭部位置不動**
3. **嘴的位置、大小固定**
4. **唯一變數 = 嘴形**

### Vivago Prompt 範本

```
Same character as reference (silver braided hair, off-shoulder cream top
with dusty-blue corset, warm amber backdrop).

Action: Mouth opens to [VISEME] shape, holds briefly, returns to rest.
No head movement, no eye movement, no expression change.
Only the mouth moves.

[VISEME] shape:
- V0 rest: closed neutral mouth
- V1 i: slightly open, lips horizontal (smiling-like)
- V2 e: half open, lips relaxed
- V3 a: wide open, lips relaxed (saying "ah")
- V4 o: round mouth (saying "oh")
- V5 u: pursed lips (saying "oo")
- V6 f: lower lip touching upper teeth (saying "f")
- V7 smile: subtle relaxed smile, mouth closed

Duration: 0.3 seconds
First frame = last frame = rest (closed neutral mouth)
```

每個 viseme 一支 mp4、命名 `sophie-viseme-<id>.mp4`。

---

## 我這邊要做什麼

### 階段 1 · 素材就位後 (Edward 產完 8 個 mp4 給我)
- 接 OpenAI Realtime audio_transcript.delta 流
- 簡易中文音節 → viseme 映射 (Python / JS 表)
- 客戶端 viseme 切換邏輯 (overlay 在現有 speakingVideo 上)
- 估時: **8-12 小時**

### 階段 2 · 整合 + 校準
- 跟現有 5/7/10 秒講話池配合 (viseme 是上層 overlay、不取代下層)
- 切換頻率調整 (太快眼睛抓不到、太慢看起來假)
- A/B 測試: viseme on vs off · Edward 體感比較
- 估時: **4-6 小時**

### 階段 3 · 上線決策
- 體感顯著提升 → merge 回主線
- 體感差別不大 → 留 branch · 改回原路
- 估時: 30 分鐘 (decision only)

**總工時**: 12-18 小時

---

## 對體驗的預期改善

| 指標 | 現在 (v2.0.42) | viseme 上線 |
|---|---|---|
| 嘴張開時機 | 跟著聲音節奏 | 跟著音節 (每個字) |
| 「啊」音時嘴形 | 隨機 (可能 O 或 E 形) | **真的大開** |
| 「噢」音時嘴形 | 隨機 | **真的圓嘴** |
| 用戶體感 | 「她在動嘴」 | **「她在說我聽到的字」** |
| 月費影響 | 0 | **0** |
| 燒 GPU | 0 | **0** |

---

## 跟主線的關係

- **不影響主線**: 這 branch 獨立、prod 用戶看到的還是 v2.0.42
- **不破壞 fallback**: viseme 失敗時自動回退到原 5/7/10 秒池
- **可隨時 merge / 砍**: 試完不滿意 = 砍 branch、prod 不受影響

---

## Edward 要做的事

1. 用 vivago 產 8 個嘴形 mp4 (規格如上)
2. 丟我桌面 / 蘇菲動畫資料夾、跟我說檔名
3. 我接 viseme 邏輯、跑通給你看效果

工時你那邊: **2-4 小時** (產 8 個短素材)

---

## Risk 紀錄

1. **嘴形貼圖會不會看起來假**: 業界做法成熟、Duix 都用、可行
2. **中文音節對照表準度**: 用最簡 8 形、不會精準、但「節奏 + 開合度對」就贏現在
3. **vivago 產的 8 個嘴形連續性**: 要求臉 / 頭不動、可能困難、若不行考慮 PNG sequence 替代
4. **跟現有講話池衝突**: viseme 是上層 overlay、底層仍跑 5/7/10 秒池當 fallback

---

*Branch v0.1 起步 · 等 Edward 產素材後接邏輯*
