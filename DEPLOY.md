# DEPLOY.md · castle-voice-engine 部署紀律（憲法級）

> 2026-05-25 ship · Edward 親口拍板強制機制
> 「不要再跟我說紀律 · 我要強制執行的解決方案」

## 唯一兩條合法部署 path

| 環境 | Command | 守門 |
|---|---|---|
| **staging** | `bash scripts/deploy-staging.sh` | 4 條自動驗收 fail → abort |
| **prod** | `bash scripts/deploy-prod.sh` | 缺 `castle/qa/edward-approved-{sha}.ok` → reject |

## 禁令

**❌ 城堡所有 agent 禁止：**

1. 直接跑 `modal deploy app.py`
2. 直接跑 `python -m modal deploy app.py`
3. 自己跑 `scripts/edward-approve.sh <sha>` 幫自己 approve
4. 繞過 `scripts/deploy-prod.sh` 寫 approval file
5. 從 detached HEAD / dirty working tree 部署 prod

**違反 = 寫進 lesson 升 critical · 同類重複 = sulima Tier B audit + 機制 rebuild**

## 為什麼有這個機制（root cause）

Edward 5/23-24 連續 catch 兩件事：
1. v0.3.2 / v0.4.0 / v0.5.0 多次 ship 沒「親自實機看」 → 結果壞東西進 prod
2. 蘇菲 cognitive 紀律寫了「ship 前 chrome MCP self-screenshot」也守不住

**結論：cognitive 紀律無效 → 必須外部 hook 強制**

prod 部署唯一 approve 入口 = Edward 親自看過 staging URL · 不靠任何 agent 自審。

## 正確流程

```text
[城堡實作]
  ↓
bash scripts/deploy-staging.sh
  ↓  (deploy app_staging.py + 4 條 auto-verify)
  ↓
[Edward 打開 staging URL 試 1 分鐘]
  ↓
Edward reply 「APPROVE <full-sha>」
  ↓
bash scripts/edward-approve.sh <full-sha>
  ↓  (寫 castle/qa/edward-approved-<sha>.ok)
  ↓
bash scripts/deploy-prod.sh
  ↓  (gate check approval file → modal deploy app.py)
  ↓
[prod 上線]
```

## 兩個 Modal app 共用 / 差異

| 項目 | castle-voice-engine (prod) | castle-voice-engine-staging |
|---|---|---|
| codebase | castle/ | 同（共用）|
| Modal secrets | openai / anthropic-key / tavus / castle-dev-bypass | 同（共用）|
| Modal volume | sophie-lipsync-cache | 同（共用）|
| Modal app name | castle-voice-engine | castle-voice-engine-staging |
| URL | edwardt0303--castle-voice-engine-fastapi-app.modal.run | edwardt0303--castle-voice-engine-staging-fastapi-app.modal.run |
| 部署入口 | app.py | app_staging.py |
| 部署 script | scripts/deploy-prod.sh | scripts/deploy-staging.sh |
| 守門 | Edward APPROVE file gate | 4 條 auto-verify abort |

## 4 條 staging auto-verify（deploy-staging.sh 內）

跑完 modal deploy 後立刻 hit staging URL：

1. `GET /health` → 200
2. `GET /static/index.html` → 200 + 含 script tag（AvatarCompositor / animation-pool.js / 任一）
3. `GET /lipsync/manifest.json` → 200 + 解析得到 phrases array
4. `GET /auth/whoami` （no cookie）→ 401

任一條 fail → staging deploy 也 abort（避免城堡 ship 廢品到 staging）。

## edward-approve.sh 行為

- 寫 `castle/qa/edward-approved-{full_sha}.ok`
- 內容：`approval_timestamp` / `commit_sha` / `branch` / `approver` / `source` / `note`
- 接受 short SHA / full SHA / test slug（dry-run）
- 蘇菲 daemon 應 catch Edward Slack/Chat reply `APPROVE <sha>` 後呼叫這個 script

## FAQ

**Q：要修 prod hotfix 急著上怎麼辦？**
A：仍走完整流程。先 `deploy-staging.sh` → Edward 試 30 秒 → `APPROVE` → `deploy-prod.sh`。
急的話縮短 Edward 試用時間，但**不繞過 approval file gate**。

**Q：staging 也要過 sulima Tier B audit 嗎？**
A：staging 屬內部試用 · 不需。但若 staging 改動觸及 secret / auth / payment → 必過 sulima。

**Q：approval file 存哪？要 commit 嗎？**
A：`castle/qa/edward-approved-{sha}.ok` · 不 commit（runtime artifact）· 已加 `.gitignore`。
跨 deploy session 持久化在本機檔系統上。

**Q：可以一次 approve 多個 sha 嗎？**
A：可以。同個 sha 重跑 `edward-approve.sh` 會覆蓋舊 file。
不同 sha 各自有獨立 `.ok` file。
