# Day 2 Current Blocker（5/22 卡西法 status）

## ✅ 已完成（不需 secret / 不需 deploy）

1. Day 1 ship `app_breeze.py` path bug fix（拿掉 `../castle`、commit b03777b）
2. Windows cp950 console encoding workaround（PYTHONIOENCODING=utf-8、寫進 SETUP.md）
3. Modal deploy 跑通（image build 113s、endpoint 上線）
4. 跟現役 `castle-voice-engine`（OpenAI Realtime）零污染確認（不同 app name）
5. SETUP.md Day 2 fix 段 ship + Day 1 完整內容保留合併
6. branch push GitHub（origin/voice-path/v2.0-breeze-poc 上線、Edward 可從 GitHub 看）
7. Day 2 research note 1：Breeze-ASR-25 model card + 10 句中文測試句 + CER 公式
8. Day 2 research note 2：4 component stack overview + A10G VRAM 預算 + cost 估算 < $10

## ⏳ Pending Edward Step 1（單一阻塞點）

Edward 跑 SETUP.md Step 1 PowerShell 3 行建 `breeze-poc-auth` secret:

```powershell
$token = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
py -m modal secret create breeze-poc-auth BREEZE_AUTH_TOKEN=$token
$token   # 印出來、複製存好
```

## 卡西法 retry 策略

Edward 下次給我 prompt 時、我**第一個動作**:
1. `py -m modal secret list | grep breeze-poc-auth`
2. 若 secret 出現 → retry deploy（secret 變更要 redeploy 才 inject 進 function env）
3. retry deploy 成功 → curl `/breeze/health` 確認 200 OK + JSON 出 `{"status":"ok",...}`
4. 開 Day 2 ASR：在 image 加 `transformers` Whisper auto-download，跑 Edward 提供的 10 句測試
5. 算 CER vs 7.97% baseline → 寫 Day 2 final note

## Edward 不必半夜起來動

我已自治處理 Day 2 開跑能做的全部工作。secret 一建好、不必跟我講、下次 prompt 我會自動 detect。

## 若 24 hr 後 secret 仍未建（escalate trigger）

- ping 主對話蘇菲：「Edward `breeze-poc-auth` secret 24h 未建、PoC 卡在 deploy auth 環節」
- 由蘇菲在自然對話時提醒 Edward 一次（不打擾、用情緒智慧 hooks 判斷時機）

## Gate 5 五條件當前狀態（更新）

| # | 條件 | Day 1 狀態 | Day 2（5/22）狀態 |
|---|---|---|---|
| 1 | 聲音樣本 never 寫 Volume | ✅ 架構符合 | ✅ deploy 後確認 Modal Volume 未掛載 |
| 2 | PoC 結束 7 天內驗零殘留 | ✅ cleanup script ship | ✅ 不變 |
| 3 | Modal account 2FA | ⚠ Edward 自證 | ⚠ 不變 |
| 4 | Modal CLI token < 90 天 | ✅ 24 天 | ✅ 25 天 |
| 5 | PoC 不接外部 / 不收客戶聲音 | ✅ X-Breeze-Token + Edward 個人 secret | ✅ 不變、待 secret 建好驗證 401 wall |

## Day 2-10 Updated Timeline

- Day 2（5/22）✅ deploy 通、Day 2 research note 2 篇 ship、等 secret
- Day 2-3（secret 後）→ Breeze-ASR-25 download + 10 句測試 + CER vs 7.97%
- Day 3-4 → BreezyVoice TTS 1 段樣本 + 延遲量測
- Day 5-6 → Picovoice Eagle 註冊（用 voice_samples/edward_for_eagle.m4a）
- Day 7-8 → Claude function calling 接城堡 7 subagent 1 demo case
- Day 9-10 → 端到端 demo + Final report + Phase 2 GO/NO-GO

## escalate 觸發條件（未變）

- Breeze ASR CER > 15%（vs 廠商 7.97%、嚴重差）
- BreezyVoice 延遲 > 2 秒
- A10G VRAM 撞滿（Breeze + BreezyVoice 同 load 超 24GB）
- Picovoice Eagle 中文聲紋註冊撞牆
- Claude function calling 接城堡 subagent 撞 issue
- Modal 月費 PoC 期 > $50

任何一條命中 = 立即 ping 蘇菲、不硬撐。
