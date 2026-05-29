# QA 紀錄 · 意思向量比對 (semantic match) · 2026-05-29

> 觸發：Edward 5/28 21:42 catch「開 ?semantic=1 變很卡 + 我講話沒回應 + 嘴一直動聽不到聲音」
> 蘇菲加 250ms debounce 修補後、5/29 正式 QA 確認
> 分工：蘇菲跑後端驗證 + 卡西法 (Gate 1) 跑瀏覽器實測 (蘇菲不自審)

---

## 結論：技術上可上線、但剩 1 個只有 Edward 能測的關卡

| 項目 | 結果 |
|---|---|
| 主線沒被弄壞 (不開 semantic) | ✅ PASS |
| semantic flag 生效 | ✅ PASS |
| debounce 真的有效 (卡的根因) | ✅ PASS · 一句話從 20-40 次後端 → 1 次 |
| 後端可達 + 命中 | ✅ PASS |
| 命中率 (15 句真實變化) | ✅ 14/15 = 93% |
| 壞輸入不會掛 | ✅ PASS (空/缺欄/英文/數字/超長/emoji 全擋好) |
| **真麥克風語音對話** | ⏳ 待 Edward 真人測 (自動測不到) |

---

## 後端驗證 (蘇菲 · python 直打 prod)

### 命中率 14/15 = 93%
意思相近的句子幾乎都命中：
- 「早安 Edward」→ Edward 早安 (0.83)
- 「Edward 早安啊」→ Edward 早安 (0.97)
- 「你想先做什麼呢」→ 早 你想先做什麼 (0.85)
- 「我等你回來喔」→ 我等你下次回來 (0.81)
- 「改天再聊囉」→ 改天聊 (0.86)
- 「我懂你的感受」→ 我懂 (0.72)
- miss 1 句：「我們開始吧」(0.50、庫裡真的沒這類)

舊 Levenshtein 字面比對這 15 句頂多 2-4 命中 → 意思比對是大幅提升。

### ⚠️ 延遲是真問題 (架構限制 · 誠實記錄)
- 冷啟：~4 秒
- 暖機平均：~2 秒
- 最慢：7 秒
- **cache 命中 (暖容器重複句)：16ms** (卡西法瀏覽器實測命中 "Edward 早安" cache)

原因：每次新句要打 OpenAI embedding API、round-trip 1-2 秒躲不掉。Modal 多容器 serverless、in-memory cache 不一定打到同一個 → 新句一律慢。

**對嘴對齊的影響**：
- 蘇菲講「新句」(大多數情況) → 比對 1-4 秒才回 → 嘴對齊 mp4 視覺**晚 1-4 秒到**
- 短句蘇菲已講完、長句還能 seek 到對的時間點接上
- debounce 解掉了「卡」(網路塞爆)、但解不掉「視覺晚到」(OpenAI 延遲本質)

### 壞輸入韌性 PASS
空字串/缺欄 → 400 乾淨拒絕；英文/數字/超長/emoji → 200 不掛、合理 miss/hit。

---

## 瀏覽器實測 (卡西法 Gate 1)

- **Test A regression**：主線頁零 JS error、avatar + Start 按鈕渲染正常、semantic 預設關正確
- **Test B flag**：`[semantic] 意思向量比對 ON` log 出現、無 error
- **Test C debounce (核心)**：程式碼 review + 真瀏覽器注入雙驗證 —
  - 同字 25 次呼叫 → 後端只 1 次 (LRU cache + in-flight dedup 生效)
  - 20 碎片快速進 (間隔 20ms) → setTimeout 只觸發 1 次、後端只打 1 次
  - **Edward 的卡從架構上解掉**
- **Test D endpoint**：POST /lipsync/match 命中 "Edward 早安" score 0.83、16ms (cache hit)

### 卡西法附帶發現 (非本次改動引入)
- 8 條 console exception = Chrome 瀏覽器**擴充**注入的、不是我們的 bug (頁面沒用 chrome.runtime)。無痕視窗看不到。
- avatar idle 影片在截圖中沒播臉 (play interrupted by new load)、主線頁也一樣、preCall 輪播切換的良性中斷。建議下個 sprint 看、不擋上線。

---

## Edward 唯一要做的驗證
無痕視窗開 `...index.html?semantic=1` → 按 Start → 真的講一句話、確認：
1. 不卡了
2. 聽得到蘇菲聲音
3. 嘴有跟著動

→ OK = merge viseme-poc-v0.1
→ 還卡 = 回報、再排查

---

---

## Round 2 · 真互動 + 視覺實測 (Edward 12:10 catch「QA 有完整做嗎? 含視覺/錄影?」後補)

上輪 (round 1) 只驗水管、沒真按 Start、把截圖裡 avatar 空白當良性帶過 = QA 不完整。
Round 2 卡西法用數據補實 3 項：

### Test 1 · avatar 空白是真 bug (不是良性、不是截圖時機)
- 冷載入第一次重現空白：readyState **0** / videoWidth **0** / currentTime 5 秒後仍 **0** 不動 = 影片凍住
- mp4 檔本身好的 (fetch 206 · 5.65MB · ftyp isom 正確) → 不是檔案問題
- **root cause = 前端 load/play race**：`avatar-director.js` 的 Director (有 _seq ownership guard) 跟 `animation-pool.js` 的 idle rotator (直接 `v.src=` + `v.play()` 繞過 guard) 搶同一個 `<video>` 元素。冷載入時 Director 初始 play 還 pending、pool 第一次 swap 就 load() → `AbortError: play() interrupted by new load request` → 影片卡 readyState 0
- **intermittent**：3 次冷載入第 1 次中、第 2/3 次贏 race 正常 → 慢/冷載偶發
- 修法：animation-pool idle swap 改走 `AvatarDirector.playIdle()` 而非直接動 src · 位置 `animation-pool.js:256-259` + `:700-703`
- **非本次 semantic 改動引入** (主線也有)

### Test 2 · 按 Start 通話閉環 = 走通 (正面)
- whoami OK 不需重登 → /sdp?model=gpt-realtime-2 **200** (確認接 GPT realtime-2、非 Tavus) → ICE connected → in-call → OpenAI session.created → ready overlay 正確消失 → 蘇菲開口 (transcript delta + speaking 律動)
- **進通話後 liveVideo readyState 4 / 1080p / 臉完整顯示** (空白只在 pre-call 冷載發生)
- 2 個非致命 503 (`/camera/enable` + `/vision/analyze_now`) = Modal 無實體攝影機、預期、不影響對話

### Test 3 · 待機動畫有在動
- 4 幀 (間隔 1.5s) 掃到 3 個不同 variant (idle/idle-2/idle-3) + 眼開↔眼閉、currentTime 有前進 = 真的在播輪播

### Round 2 結論
| 項目 | 結論 |
|---|---|
| 蘇菲視覺 (進通話) | 完整正常 |
| 待機動畫 | 有動 |
| 通話閉環 | 走通到「需真人麥克風」前一步 |
| 真 bug | pre-call idle 影片 intermittent race (冷載偶發空白) · 修在 animation-pool.js |
| 剩 Edward 測 | 真人講話 → OpenAI 回應 → 蘇菲回應內容對不對 (headless 無真人聲音) |

### 截圖落地誠實說明
Chrome MCP save_to_disk 只存進 harness 附件庫 (對話內可看)、沒落到 outputs\_qa_round2\ 實體檔。工具限制、不假裝有寫。

---

## 學到的事 (進死路備忘錄)
**「意思比對解了命中率、但 OpenAI embedding 延遲 1-4 秒讓即時嘴對齊視覺晚到」**
→ 即時嘴對齊若要 < 0.5 秒、得換更快的比對方式 (本機跑的小模型 / 預算 embedding)、
   或接受「嘴對齊是 best-effort 晚到、靠底層 speaking.mp4 撐即時」。
