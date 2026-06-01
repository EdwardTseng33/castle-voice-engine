# Voice Path 死路備忘錄（憲法級 · 技術決策前必讀）

> 立檔：2026-05-27（Edward 親口拍板「請作一個備忘錄知道我們曾經嘗試過什麼方向是不通的、原因是什麼。然後你要能在做任何技術決策之前要先看過這個備忘錄」）
>
> 用途：避免重蹈覆轍。任何蘇菲 / 城堡 agent 在 voice-path 做技術決策前必先讀過這份。違反 = 同類問題重犯 = 升 critical。

---

## 鐵律

1. **任何 voice-path 技術提議前**，必先讀完本檔 + 對照「死路清單」。
2. 若新提議 **看起來像** 某條死路 → 必明文說明「跟過去 X 路差異在哪、為何這次能通」、再動手。
3. 若拿不出差異 → **不動**，等 Edward 拍板。
4. 同類撞牆 ≥ 3 次 = 升憲法級 + 強制砍架構重來（v5.4.24）。

---

## 產品方向 · Avatar 主攻「擬真」（2026-06-01 Edward 拍板 · 多輪校準）

> 背景：6/1 Edward 問「原生 App 上架 + Unity 3D avatar」兩題、城堡 council（卡西法技術 + 霍爾競品）給 verdict。卡西法挖到「web 3D（Three.js + VRM）成本 0、能任意句子對嘴」這條技術金路、但臉是卡通/虛擬偶像風。Edward 三輪校準後定錨。

**方向定錨（做 avatar 視覺決策前必看）：**
1. **主力追求 = 擬真**：把角色做成「看起來像真人」（照片級擬真）。這是現在主攻的方向。
2. **角色原型 = 動畫《霍爾的移動城堡》的蘇菲**：現在的蘇菲 avatar 就是以動畫蘇菲為原形、做成擬真版。未來換別的人物設計 OK、但精神是「以某個角色為原型 → 做成擬真」。
3. **卡通 / 虛擬偶像 / 動畫風 = 不排除**：未來可能還是會有、或作為其他選項並存。**只是現在主攻的不是那個。** 要走卡通/動畫風 = 需 Edward 額外拍板、不是預設。
4. **預設原則**：做 avatar 視覺升級時，預設往「擬真」走（真人影片 / 未來照片級擬真真人合成如 Tavus Phoenix-4）。
5. **競品參考**（霍爾）：真人影片派（Tavus/HeyGen）在「親密陪伴」場景領先；3D 寫實要留意恐怖谷。

**用法**：avatar 視覺方向預設「擬真」；提卡通/動畫/web-3D 省成本路線前，先確認 Edward 是否要、不自作主張當成主力。

---

## 死路清單（依時序）

### A · MuseTalk 即時 lipsync（v3.0 ~ v3.3 · 5 次失敗）

**試過什麼**：用 MuseTalk 神經網路、即時把音講話的蘇菲嘴對齊。

**為什麼不通**：
- 需 A100/H100 才能即時（A10G 跑出來 RTF 3.2、太慢）
- A100/H100 月費 NT$ 120,000-200,000、爆 Edward NT$ 2,000/月預算 **100 倍**
- Edward 5/27 自己 catch：「Duix 不可能用 A100/H100 服務每個用戶」=  業界輕量路線根本不是 GPU 神經網路

**根本教訓**：
- 業界 Duix / Tavus / HeyGen 都不是「即時神經 lipsync」這條路、是「預錄 + 嘴形貼圖」混合架構
- 即時神經 lipsync = 學術 / demo 玩具、不是產品架構
- 任何「即時 GPU lipsync」提議 = 自動拒絕、除非明文說明跟 MuseTalk 路線差異

---

### B · SoulX-FlashHead PoC（v0.3.2 · 7 次失敗）

**試過什麼**：接 SoulX-FlashHead 開源 lipsync 模型。

**為什麼不通**：
- 連續 4-7 次走錯路、根本沒看官方 README
- 自行排列組合套件、撞「跟 tested versions 不對齊」之牆

**根本教訓**：
- **接外部模型前必先讀 README + requirements + tested versions**
- 已立規矩：`memory/feedback_third_party_tool_official_docs_first.md`
- 違反 = critical 等級

---

### C · Tavus CVI 整合走錯（5/23-5/24 · 4 次連錯）

**試過什麼**：v0.3.2 / v0.4.0 / v0.4.1 / v0.4.2 / v0.5.0 把 Tavus 當 end-to-end 用、想用它做語音 + 嘴對齊一條龍。

**為什麼不通**：
- 我們**已經有** GPT realtime2（即時對話）+ Breeze ASR（聽寫）在後端跑
- 我把 Tavus 當 end-to-end = 跟既有架構打架
- Edward 凌晨 catch：「我們語音服務不是用的是 GPT 的 realtime2 嗎？」

**根本教訓**：
- **接外部工具前必先 grep project 既有架構**
- 已立規矩：feedback_third_party_tool_official_docs_first 第 5 道 gate
- 任何「換掉 GPT realtime」提議 = 必明文說明為何要換、跟既有路徑差異

---

### D · LiveKit WebRTC SFU 換架構（v0.10 Phase 2 · 卡住）

**試過什麼**：想砍 Modal 直接 WebRTC 架構、改走 LiveKit SFU。

**為什麼不通**：
- Modal 跟 WebRTC publisher 模式不相容
- 砍架構前沒先確認替代架構真的能跑

**根本教訓**：
- **架構懷疑紀律（v5.4.24）**：砍架構前必先確認替代架構在 PoC 過、不是「聽起來合理」就動
- 任何「砍 Modal / 砍 WebRTC」提議 = 必先小 PoC 驗證

---

### E · viseme 整圖切換（2026-05-27 · 今天踩）

**試過什麼**：從 sophie-speak-10s.mp4 抽 8 張定格、200ms 切一張當「嘴形 overlay」。

**為什麼不通**：
- 8 張定格是**整張臉**、不只嘴
- 200ms 切一張 = 整個畫面跳格、底層會呼吸眨眼的蘇菲被完全蓋住
- 結果像投影片在跳、不是 Duix 那種「身體一直動、嘴跟著音換」

**根本教訓**：
- **Duix 是兩層架構**：底層蘇菲影片一直動 + 上層只疊「嘴」這個小元件 + 嘴位置鎖到底層臉的座標（頭擺嘴跟著擺）
- 整圖切換 ≠ viseme = 業界 lipsync 兩條完全不同的路
- 任何「整圖 overlay」提議 = 自動拒絕

---

### F · 想靠抽現有影片 frame 自動產嘴部素材

**試過什麼**：（內部想過）從蘇菲影片偵測嘴部 + crop 出來當嘴貼紙。

**為什麼不通**（未實作、但已分析）：
- 8 張原圖蘇菲頭位置不完全一樣、偵測到的嘴部位置每張會偏 5-10 像素
- 貼到底層動畫上會「嘴在臉上飄」、比現在更糟

**根本教訓**：
- 嘴貼紙需要**先有對齊好的純嘴素材**（vivago 產的嘴部特寫透明背景）、不是事後 crop
- 任何「自動偵測 + crop 嘴部」提議 = 必先 PoC 驗證對齊精度

---

### G · LatentSync 本機 fine-tune（霍爾 5/23 調研後 hold）

**試過什麼**：用 LatentSync 1.6 + 蘇菲 30 分鐘訓練影片、本機 RTX 4090 fine-tune。

**為什麼 hold**（不算失敗、是時機判斷）：
- 霍爾 5/23 verdict：「**不立刻啟動**、嘴對齊不是當前 Edward 真實 friction」
- 訓練成本 $13-26 一次、加上「拍 30 分鐘真人蘇菲」NT$ 18k-35k
- 結論：終局繞不開、但 v1.0 階段先用 Replicate 預錄方案撐

**啟動時機（任一達成）**：
1. Edward 用 v1.0 滿 2 個月 + 3 次「嘴沒對齊有點出戲」真實 friction
2. Voice Path v0.5+（對外分身）需要更真實對話分身
3. LatentSync 1.7+ / daVinci fine-tune path 出來

**根本教訓**：
- 不每個技術選項都要做、要看 friction 訊號
- 完整研究存：`docs/v2.0-lipsync-research-howl.md`

---

### H · 補丁式修嘴 timing（v2.0.39 ~ v2.0.42 · 4 個版本連修）

**試過什麼**：拚命修「講 10 秒動畫只 5 秒」、「audio.done 太早 stopSpeaking」等 timing 問題、4 個版本連續 patch。

**為什麼不通**：
- 補了 4 個版本還是會跑出新 timing bug
- 根本問題：底層只有一個 mp4 loop、對任意句子嘴都不對

**根本教訓**：
- **同類 bug ≥ 3 次 = 砍架構（v5.4.24）**、不是繼續 patch
- 4 個版本連 patch = 違反這條紀律、Edward 5/27 catch 後立鐵律

---

## ✅ 正確路線（已驗證）

| 路線 | 狀態 | 證據 / 用法 |
|---|---|---|
| **GPT Realtime API（gpt-realtime-2 + marin voice）** | ✅ 線上跑 | 即時對話通道、原 prod 主路 |
| **OpenAI gpt-4o-mini-tts**（離線 TTS） | ✅ 試過 | coral 女聲 + instructions 控口吻、可離線產任意句 |
| **Replicate `sync/lipsync-2-pro`**（v1.5.0 預錄 100 句） | ✅ 線上跑 | $0.09/句、Edward 5/23 評過效果好、目前 prod 嘴對齊 cache 全部用這個 |
| **PhraseMatcher fuzzy match** | ✅ 線上跑 | Levenshtein 距離模糊比對、100 句 hit 率不夠（句子涵蓋面太窄）|
| **Claude Haiku 4.5 vision**（前端送 frame） | ✅ 線上跑 | 月預算 $3、`/vision/analyze_now` endpoint |
| **Modal + FastAPI** | ✅ 線上跑 | 主部署環境、含 Volume cache（sophie-lipsync-cache） |
| **預錄招呼 cache + barge-in**（v2.0.42） | ✅ 線上跑 | Start 時馬上有聲、用戶開口立刻 cancel |

---

### I · 意思向量比對 · 命中率解了但延遲沒解（2026-05-29 · 半通）

**試過什麼**：把嘴對齊比對從 Levenshtein 字面距離換成 OpenAI text-embedding-3-small 意思向量 + cosine。

**結果**：
- ✅ 命中率大幅提升（14/15 = 93%、舊字面比對頂多 2-4）
- ✅ debounce 解掉「卡」（一句話 20-40 次後端 → 1 次）
- ⚠️ **延遲沒解**：新句要打 OpenAI embedding API、round-trip 1-4 秒躲不掉（cache 命中才 16ms、但 Modal 多容器 serverless、cache 不可靠）

**根本限制**：
- 即時嘴對齊需要 < 0.5 秒比對、但 OpenAI embedding 1-4 秒 = 嘴對齊視覺晚到
- 短句蘇菲已講完、長句還能 seek 接上
- 結論：**意思比對適合「離線預先算好」、不適合「即時逐句比對」**

**根本教訓**：
- 任何「即時逐句呼叫雲端 API」提議 = 必先量延遲、> 0.5 秒就不適合放在即時對話 critical path
- 即時嘴對齊要快、得用本機跑的小模型 / 預先算好的 embedding、不是即時打 OpenAI
- 完整 QA：`docs/qa-semantic-match-2026-05-29.md`

---

## ⚠️ 未驗證待嘗試（先小 PoC）

| 路線 | 風險 | 先驗證什麼 |
|---|---|---|
| **擴 Replicate 預錄 100 → 300-500 句** | 低（同已驗證路線、~$36 一次） | 10 句小批跑、Edward 試聽 OK 才跑剩下 |
| **嘴部透明圖 + 臉部辨識動態貼合**（Duix 兩層架構正版） | 中（嘴位對齊精度未驗） | 先用 1 張嘴貼紙 + 1 句測、看跟底層臉的對齊偏差 |
| **真人版蘇菲 + LatentSync fine-tune** | 高（NT$ 18-35k 投資） | 等 Edward 累積真實 friction 訊號（霍爾 verdict 3 觸發點任一達成） |

---

## 決策前 SOP（給未來蘇菲 / agent）

1. **讀本檔全文**（不准跳過）。
2. **比對提議跟死路清單**：
   - 看起來像 A-H 任一條 → 明文寫「差異在哪」、否則不動。
   - 看起來像 ✅ 已驗證路線 → 直接動。
   - 看起來是新方向 → 列「跟既有架構衝突點」、Edward 拍板才動。
3. **PoC 小規模先試**：
   - 任何「跑很多 / 花很多錢 / 改架構」都要先 1-10 次驗證。
4. **完成後更新本檔**：
   - 新撞到牆 → 加進死路清單。
   - 新驗證通 → 加進 ✅ 正確路線。

---

## 更新紀錄

- 2026-05-27 初稿 · 蘇菲整理 8 條死路 + 7 條已驗證路線
- 後續每碰新牆 / 開新路、附上日期 + 撞牆原因 / 通過證據

---

*本檔位置：`docs/voice-path-deadends-memo.md`*
*交叉參照：`STATUS.md`（頂部加引用）、Moving Castle `memory/MEMORY.md`（索引）*
