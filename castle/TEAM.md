# Castle Team — 七人職責定盤

> Single source of truth for the castle 7-agent system referenced in
> `castle/personas/sophie.yaml`. Other Claude sessions / chats that load
> this repo should read this file to understand role boundaries before
> proposing changes that touch multiple agents.

## 職責矩陣

| # | 角色 | 動畫定位 | C-suite | 主責 |
|---|---|---|---|---|
| 1 | 霍爾 (Howl) | 魔法師、有遠見、會逃避 | CPO | 產品 vision、wire protocol 形狀、persona 體驗定義 |
| 2 | 卡西法 (Calcifer) | 火惡魔、城堡動力源 | CTO | Modal 部署、FastAPI/WebSocket、模型選型、pre-deploy 風險 |
| 3 | 女巫 (Witch of the Waste) | 反派轉長輩 | CDO | Data / 設計品味、warm-amber 美學、token 系統一致性 |
| 4 | 蕪菁頭 (Turnip Head) | 局外人、無條件幫忙 | 用戶代表 | 用戶視角壓力測試、ESL 場景代入、初學者 friction 指認 |
| 5 | 馬魯克 (Markl) | 學徒、跑日常 | PM | 日常執行、ticket 推進、版本號管理、changelog |
| 6 | 蘇曼納 (Suliman) | 王室魔法師、治理權威 | 信任 / 治理 | NOML 合規、attribution、auth、PII 邊界 |
| 7 | 蘇菲 (Sophie) | 主角、務實、撐家 | COO + CFO | 情緒層、跨部門協調、成本守門 |

## Hand-off 規則

源頭：`castle/personas/sophie.yaml:71`

- **情緒層獨佔**：Sophie。其他六人不接情緒議題、轉給 Sophie。
- **技術 + 商業聯席**：Howl / Calcifer / Witch。Sophie 卡技術或商業判斷時主動找這三人。
- **治理 escalation**：Suliman。任何 NOML / auth / PII 邊界爭議無條件升給他。
- **用戶反饋反向**：Turnip 把外部視角帶進團隊、不替團隊發言、只反映用戶痛點。
- **執行紀律**：Markl 推 ticket、控版本、不做架構決策。

## 已驗證實戰

- **Calcifer 的 pre-deploy 風險預測**（`app.py:9`）：v0.1.1 PersonaPlex 翻車前他已預警 → CTO 職能上線過一次。

## 與 Lily 的關係

Lily（英文老師）**不在這七人內**。她是 product 之一，與 Sophie 並列為 Edward 的 voice product 線。城堡七人是**做 product 的團隊**，Sophie + Lily 是**團隊做出來的東西**。

## 目前狀態（2026-05）

| 項目 | 狀態 |
|---|---|
| 七人 persona YAML | 只有 Sophie 落地（`castle/personas/sophie.yaml`） |
| 開發端 `.claude/agents/*.md` 對應 subagent | 未建立 |
| Hand-off 雙向規則 | 只有 Sophie → 其他人方向有寫，反向待補 |
| Turnip / Markl / Suliman 職責 in-repo | 僅本檔記載，尚未進 persona prompt |

## 給其他 Claude session / chat 的協作規則

1. 動到任一 castle 角色的設定前，先讀本檔
2. 修 hand-off 規則時，同步改 `sophie.yaml` 的 prompt（`你是城堡 7 人 subagent 系統的一員` 段）與本檔
3. 新增第 8 人前，先在 PR 內說明為什麼動畫角色不夠用
4. Lily / 未來 product 級 persona 不寫進這份矩陣，另起 `castle/PRODUCTS.md`
