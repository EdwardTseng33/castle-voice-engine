# Phase 3.2 SoulX-FlashHead 整合計畫書 · 蘇菲長真臉

> v1.0 · 2026-05-22 · 蘇菲在 Modal demo 跑著的同時預先寫
> Modal demo 跑通驗證質感 OK → 此計畫書立刻動手、不必到時候才想

---

## 北極星對齊（不變）

「讓 Claude 長出前端的臉和嘴、自然像同事討論工作」（Edward 4/29 親口）

Phase 3.2 = **把 castle-voice-engine 既有的 SVG 簡筆蘇菲頭像、換成 SoulX-FlashHead 生成的 photo-real 即時動的真臉**。

---

## 範圍

### In scope
- 用 SoulX-FlashHead 1.3B Lite 替換 `castle/static/index.html` 內 SVG 蘇菲頭像
- 嘴型同步接 OpenAI gpt-realtime-2 的 audio output stream
- 表情狀態（idle / speaking / sleep）接 SoulX 的 condition 機制
- 直播感版面整體保留（女巫 spec State A / B / C 全套不動）
- Modal 跑 inference（Edward Python 3.14 fallback 確定走雲）

### Out of scope
- face-gated voice（Phase 3.1.2+ 範圍 · Sally / Qiana 認臉認聲 hard rule 守住）
- 多人入鏡 layout（女巫 State C · Phase 3.2.x）
- 桌面情境感知（pywin32 · 你拍板）
- 商業化（ADR-020 Track B · 仍 NO-GO · 公開要重審）

---

## 架構

```
                  ┌──────────────────────────────────┐
                  │ Browser (castle/static/index.html)│
                  │                                   │
   Edward         │  Web Audio capture ────┐          │
   麥克風 ────▶ │                          │          │
                  │  ┌─────────────┐       │          │
                  │  │ gpt-rt-2    │ audio │          │
                  │  │ WebRTC peer │ output│          │
                  │  └──────┬──────┘       │          │
                  │         │              │          │
                  │         ▼              │          │
                  │  ┌──────────────────┐  │          │
                  │  │ SoulX video      │◀─┘          │
                  │  │ frame iframe /   │             │
                  │  │ canvas (替換 SVG) │             │
                  │  └────────┬─────────┘             │
                  └───────────┼──────────────────────┘
                              │ websocket frame stream
                              ▼
                      ┌──────────────────────┐
                      │ Modal A10G           │
                      │ soulx-flashhead-poc  │
                      │                      │
                      │  /soulx/stream       │ ← WebSocket endpoint
                      │  接 audio chunks     │
                      │  生成 video frames   │
                      │  回 WebSocket frames │
                      └──────────────────────┘
```

---

## 改動清單

### castle/server/soulx_endpoints.py（新檔 · 估 200 行）

新增 FastAPI WebSocket endpoint `/soulx/stream`：
- 收 audio chunk（16kHz mono PCM16 bytes）
- 串接到 Modal `run_inference` 的 streaming variant
- 把生成的 video frame stream 回 browser

### castle/static/index.html（改 · 替換 avatar zone）

當前 SVG 簡筆蘇菲頭像區塊：
```html
<div class="sophie-avatar">
  <svg class="sophie-face" viewBox="0 0 100 100">
    ...
  </svg>
</div>
```

替換成：
```html
<div class="sophie-avatar sophie-avatar-real">
  <canvas id="sophieRealCanvas" width="380" height="380"></canvas>
</div>
```

JS 新增 WebSocket client 接 `/soulx/stream`：
- 開對話時、把 gpt-realtime-2 audio output stream 同時送一份到 `/soulx/stream`
- 接收 video frame → draw canvas
- idle / speaking / sleep 狀態仍對齊 Phase 3.1.1 既有動畫邏輯（呼吸燈邊框、待機呼吸等）

### app.py（改 · mount /soulx routes）

```python
from castle.server.soulx_endpoints import attach_soulx_routes
attach_soulx_routes(fastapi_instance)
```

### castle/personas/sophie.yaml（小改）

加 `visual_persona` 段：
```yaml
visual_persona:
  reference_image: assets/sophie_warm_amber.png  # 暖琥珀風蘇菲參考照片
  model: soulx-flashhead-1.3b-lite
  inference_endpoint: /soulx/stream
```

### models/ 防漏（已 gitignore）

13.67 GB SoulX-FlashHead weights 永遠不上 git、永遠不上其他雲（除 Modal Volume）。

---

## 工時切分

| 階段 | 工作 | 工時 |
|---|---|---|
| 3.2.1 · Modal streaming endpoint | 把 generate_video.py 改成 streaming WebSocket 模式（接 audio chunk → 即時吐 frame） | 3-5 hr |
| 3.2.2 · 蘇菲參考照片 | Edward 選 / 女巫設計 1 張「暖琥珀風蘇菲」reference 照片（PNG 512×512） | 1-2 hr |
| 3.2.3 · castle-voice-engine WebSocket relay | 寫 soulx_endpoints.py + 接 Modal endpoint | 2-3 hr |
| 3.2.4 · index.html avatar 替換 | SVG → Canvas + WebSocket client + 同步 idle/speaking | 2-3 hr |
| 3.2.5 · 整合測試 | end-to-end demo · 確認 lip sync 對得起 + 延遲 < 1s | 3-5 hr |
| 3.2.6 · Phase 3.1.1 動畫對齊 | 呼吸燈邊框 / 待機呼吸 / sleep 跟真臉融合（不打架） | 2-3 hr |
| 3.2.7 · 暖琥珀 DNA 整合 | 真臉背景 / 邊框 / 環境光對齊既有 token | 1-2 hr |
| **合計** | | **14-23 hr 人類 / 4-7 hr 城堡** |

---

## Edward 邊界（ADR-020 Track A + sulima #5 spec）

- ✅ Edward 自己樣本 OK
- ✅ Qiana informed consent OK
- ⚠ 訪客 / 旁邊路過的人不主動錄
- ⚠ 真有未成年互動場景出現時、屆時以真實需求重做安全機制（v0.3.0 移除原「Sally 6 歲」hard rule · 記憶污染、實際無此對象）
- ❌ 不對外公開生成的 clip（除非重審 Track B）
- ❌ 不上中國雲（仍守 Modal 美國雲架構）

---

## 接 Modal demo 結果的對齊判斷

Modal demo 跑通後、看 3 件 verify 質感是否值得整合：

1. **lip sync 對得起 Edward 5/21 64 秒錄音的內容**（嘴型跟聲音吻合度）
2. **臉部表情自然度**（不要 uncanny valley · 暖琥珀風適配）
3. **延遲 / 流暢度**（A10G 上 25+ FPS · 跟對話 < 1s gap）

任一項不過 → 暫不整合、等更新版 SoulX-FlashHead Pro / 西方競品 mature。

---

## 跟既有 Phase 3.1.1 直播感版面的相容

Phase 3.1.1 ship 的：
- 雙欄 layout（左 avatar / 右 selfie）
- 收音波形 + 呼吸燈
- mic toggle / camera toggle
- 暖琥珀 DNA token 6 個新

Phase 3.2 只動 **左欄 avatar 內容**（SVG → Canvas + 真臉 stream）、其他**全部不動**。

直播感版面架構 = 永久 baseline、Phase 3.2 只升級 avatar 質感、不重做 layout。

---

## Watch list（不卡 Phase 3.2 · 月度掃描）

- Boson Higgs Avatar v2 / v3（美國 · Li Mu · 過往 Audio 系列都 Apache 開源 · 等 v2/v3 釋出 self-host）
- Hedra（美國 · 即時對話 photo-real）
- Tavus（美國 · 從 personalized video pivot 即時對話）
- Meta / Google 西方大廠真人質感開源

任一 mature 出 Apache 2.0 + 本機跑路線 → Phase 3.3 評估換主路、Phase 3.2 SoulX 退備位（或保留作 fallback）。

---

## 完成定義（Phase 3.2 算 ship 的標準）

- ✅ Modal SoulX streaming endpoint 接通
- ✅ castle/static/index.html 真臉 Canvas 替換 SVG
- ✅ Edward 自己跟蘇菲對話 5 分鐘、嘴型對得起、自然
- ✅ 暖琥珀 DNA 整合（背景 / 邊框 / 環境光）
- ✅ Phase 3.1.1 既有動畫（呼吸燈 / 波形 / mic toggle）全保留可用
- ✅ Sally 邊界寫進程式（hard rule）+ 黑名單 check
- ✅ Modal 月費估算（Edward 真實用量觀察 1 週後算）
- ✅ commit + push voice-path/v0.3.2-soulx-flashhead-poc → merge 進 v0.3.0-phase3-camera（或開 v0.3.2 release 分支）

---

*v1.0 · 2026-05-22 · 蘇菲在 Modal demo 跑著的同時預先寫 · demo 質感 OK → 此計畫書立刻動手*
