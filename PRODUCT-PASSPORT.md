# BeyondVoice 引擎（castle-voice-engine runtime）· 產品護照

> 🔔 **2026-06-25 正式定名**：本產品對外名 = **BeyondVoice**（舊名 Voice Path 退役）。本檔描述的是 BeyondVoice 的**底層引擎** `castle-voice-engine`（技術代號、不對外露出）。定名詳情：`E:\BeyondVoice\00-定名與地圖\BeyondVoice-正式定名-2026-06-25.md`

> 套用範本：`~/.claude/protocols/product-passport-template.md`
> 配合 SOP：`~/.claude/sops/v5.4.x/v5.4.22-multi-product-portfolio.md`
> 建立日：2026-05-21 · 蘇菲首次填入、缺項標「待 Edward 補」
> 注意：本檔在 castle-voice-engine（語音引擎 backend）目錄。Voice Path 作為消費者產品的前端 / 商業層可能在別處、待 Edward 釐清

---

## § 1. 願景 / 為什麼存在

即時語音版蘇菲（city 蘇菲 → 語音蘇菲）。base on NVIDIA PersonaPlex 7B + Kyutai Moshi、跑在 Modal A10G、目標 cold start 30s / warm RTT < 250ms。

中長期：讓蘇菲 persona 不只是文字 / chat、而是真即時語音夥伴。

## § 2. 定位 / 目標用戶

- **主要**：Edward 個人 + 城堡內部 dogfood（蘇菲語音化）。長期擴展到城堡 framework 開源 / 商業化情境
- **不是**：通用語音助理（不是 Siri / Alexa 替代）、不是 call center 商業（單 tenant inference 限制）

## § 3. 設計 DNA

### 語音風格
- persona：sophie（在 `castle/personas/sophie.yaml`）
- 語音 DNA 待 Edward 補（聲音調性 / 語速 / 情感曲線 / 沉默規則）

### 文字 / 互動風格
- 蘇菲人格（user-level CLAUDE.md 已定義）
- 語音場景額外考量：等待感、打斷處理、確認反饋（待補）

## § 4. 當前狀態

- **階段**：runtime backend 已建（app.py + Modal deploy + WebSocket /voice + persona registry）
- **最新版本**：待 Edward / 卡西法補（git log 可看）
- **上線網址**：未上線消費者版（runtime 為主、frontend 端待建）
- **License**：NVIDIA Open Model License (NOML) + Kyutai Moshi MIT
- **下一步**：待 Edward 補（frontend 接 / Modal deploy / dogfood 順序）
- **參照狀態**：`README.md` + `app.py` + `castle/server/engine_server.py`

## § 5. 真實用戶 feedback 來源

- **真實用戶聯絡管道**：dogfood 階段 = Edward 自己跑、feedback = 自己感覺
- **回饋頻率**：待 dogfood 啟動
- **負責人**：Edward + 蘇菲
- **回饋紀錄位置**：建議 `test_outputs/` 旁邊建 `dogfood-notes-YYYY-MM-DD.md`
- **當前缺口**：消費者版未上線、無真實外部用戶

## § 6. 競品紀錄

語音 AI / agent 競品池待補：OpenAI Voice Mode / ElevenLabs / Sesame AI / Hume AI / Vapi（卡西法週技術掃描可涵蓋）

## § 7. 失誤 / lesson 紀錄

待累積（runtime 階段、早期 lesson 應有）

## § 8. 對外政策

- **Tier A-B 自決**：runtime 優化 / persona yaml 調整 / Modal 部署細節
- **Tier C 必先 Edward 拍板**：licensing 變動 / NOML attribution / 上線給外部使用者
- **NO-GO**：對外發佈未過 NOML attribution（4 段 attribution 必加 · 詳 `LICENSE.NOML`）

## § 9. 城堡團隊配置

- **主力**：卡西法（Modal / FastAPI / WebSocket 架構 + 部署）+ 沙利曼（NOML license / attribution）
- **特例**：蘇菲 persona 本身的對話質量由蘇菲 + 蕪菁頭 dogfood feedback 主導

## § 10. 跨產品共用素材

- **跟其他城堡產品的關係**：本質是城堡內部基礎建設、長期可作為城堡 framework 商業化的一塊
- **共用 persona**：sophie.yaml ≈ user-level CLAUDE.md 蘇菲人格 + 語音層細節
- **架構互通**：Modal scale-to-zero 經驗未來可借鑑其他產品 backend

---

## 待 Edward 釐清

1. Voice Path 作為消費者產品的前端 / 商業層在哪？（castle-voice-engine 只是 runtime backend）
2. dogfood 上線時間表
3. 語音版蘇菲的人格與文字版蘇菲是同一個還是有差異

---

*v0.1 初版 · 2026-05-21 · 蘇菲填入、Edward 待補 § 3 語音 DNA + § 4 上線細節 + 上述 3 點釐清*
