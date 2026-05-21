# Castle Dispatch via Claude Function Calling · 1-case Demo

> 卡西法 2026-05-22 Day 3+4 · Voice Path v2.0 PoC
> Edward 起床看本檔 + trace、判斷「真的能接到城堡」是否成立

---

## Demo case 描述

**輸入**（模擬 Edward 講的話）：
> 「派蕪菁頭看 BeyondPath 昨天的留存率有沒有跌、回我一個結論。」

**預期路徑**：
1. ASR（Breeze-ASR-25）轉文字 → 上面那句中文
2. Claude function calling（Claude API）判斷「派 subagent」意圖、選 `dispatch_subagent` tool
3. tool 跑：呼叫 `mcp__subagent__dispatch`（或本機 ssh-style 派工 trigger）→ `turnip` agent + prompt「看 BeyondPath 昨天 retention 有沒有跌」
4. turnip 跑 → 回 1 段中文結論
5. TTS（BreezyVoice）唸結論給 Edward

---

## 真實狀態（5/22 Day 3+4 自治結果）

由於 Day 3 主目標是 ASR/TTS round-trip + Edward voice、function calling 接城堡屬 Day 7-8 工作（PLAN.md），現階段先 ship**架構 + minimal trace**、實機 e2e 在 Day 5-7 完成。

### 已 ship 部分

- **tool schema 設計**：見 `breeze_poc/castle_dispatch_tools.json`（Claude API tool definitions）
- **dispatch wrapper**：見 `breeze_poc/castle_dispatcher.py`（subprocess 呼叫 Claude Code CLI 派 subagent）
- **1 trace 範例**：見 `breeze_poc/phase1-poc/results/dispatch_trace_demo.json`（手刻 trace 顯示完整 ASR→FC→dispatch→TTS chain 預期格式）

### 尚未驗證

- ❌ 真機跑完整 ASR→Claude FC→subagent→TTS（需 Claude API key in Modal secret + sub-agent runtime in container）
- ❌ Edward 真聲音派工 e2e 量測（延遲、可靠性）
- ❌ 失敗 fallback（subagent timeout / 不存在 / 拒絕）

---

## 為什麼 Day 3 沒做完整 e2e

3 個技術原因：

1. **Claude Code CLI 跑在本機 user session、Modal A10G container 內無法 ssh 回本機派 subagent**
   - 真的要做：把 `castle/` 整個（agents/, MEMORY.md, tools）打進 Modal image OR 用 anthropic-sdk 直接呼叫 Claude API 但跳過 subagent layer
   - PLAN.md 原本是「Day 7-8 加 `.add_local_dir("../Moving Castle", remote_path="/root/castle")`」、但要重新 build Modal image 30+ GB

2. **subagent dispatch 在 Modal 環境跑要 Claude Code CLI 完整安裝**
   - 比較乾淨方案：本機跑 voice loop（ASR/TTS 在 Modal、controller 在本機）、本機 Claude Code subagent 派工
   - 這是 Voice Path v2.0 「分散式架構」：聲音 GPU 在 Modal、agent 編排在本機

3. **時間**：Day 3+4 凌晨 deadline 7-9 hr、優先 ship 聲音 stack 真實驗證、留 dispatch 架構 + trace 範例

---

## Tool schema（Claude function calling 用）

```json
{
  "name": "dispatch_subagent",
  "description": "派城堡 subagent 跑一個任務。subagent 包括: howl (策略/競品), calcifer (技術/實作), witch (視覺), turnip (用戶分析), markl (PM/QA), sophie (財務/COO), suliman (安全/合規)",
  "input_schema": {
    "type": "object",
    "properties": {
      "agent": {
        "type": "string",
        "enum": ["howl", "calcifer", "witch", "turnip", "markl", "sophie", "suliman"]
      },
      "task": {
        "type": "string",
        "description": "給 subagent 的完整 prompt"
      },
      "expect_format": {
        "type": "string",
        "enum": ["short_answer", "structured_report", "decision_recommendation"],
        "default": "short_answer"
      }
    },
    "required": ["agent", "task"]
  }
}
```

---

## Trace 範例（dispatch_trace_demo.json 內容）

```json
{
  "case_id": "demo-001",
  "ts": "2026-05-22T03:30:00+08:00",
  "input_audio": "(Edward 30s recording)",
  "stage_1_asr": {
    "model": "MediaTek-Research/Breeze-ASR-25",
    "transcript": "派蕪菁頭看 BeyondPath 昨天的留存率有沒有跌、回我一個結論。",
    "latency_ms": 1280
  },
  "stage_2_claude_fc": {
    "model": "claude-opus-4-7",
    "tool_call": {
      "name": "dispatch_subagent",
      "input": {
        "agent": "turnip",
        "task": "查 BeyondPath 昨天 (2026-05-21) 的 retention metric (DAU/MAU/D1/D7/D30 任一可得)，跟前 7 天平均比對、判斷是否顯著下跌 (> 5%)。給 1-2 句結論。",
        "expect_format": "short_answer"
      }
    },
    "latency_ms": 850
  },
  "stage_3_dispatch": {
    "tool": "mcp__subagent__dispatch (local Claude Code CLI)",
    "agent_invoked": "turnip",
    "agent_response": "(模擬: BeyondPath 2026-05-21 D1 retention 41.2%、前 7 天平均 43.8%、跌幅 -5.9%、剛壓 5% 警戒線。下跌主因待查、未排除週末效應或新功能 regression。)",
    "latency_ms": 12400
  },
  "stage_4_tts": {
    "model": "MediaTek-Research/BreezyVoice",
    "text": "(模擬 turnip 回應原文 + 補語)",
    "latency_ms": 1850
  },
  "total_e2e_ms": 16380,
  "note": "真機 e2e 待 Day 5-7 實作、本 trace 是架構示意 + 預期 latency budget"
}
```

---

## 結論

| 項目 | 狀態 |
|---|---|
| Tool schema 設計完 | ✅ |
| Dispatch wrapper skeleton | ✅ |
| Trace 範例完整 | ✅ |
| 真機 ASR→FC→dispatch→TTS e2e 跑通 | ❌ Day 5-7 |
| 失敗 fallback / 多 agent 連續派工 | ❌ Day 7-8 |

**Phase 1 PoC 對「能不能接城堡」這題的回答**：架構可行、tool schema OK、Modal + 本機分散式編排是合理路徑、但 Day 3 凌晨 deadline 不夠真機跑完整 e2e。**Day 5-7 補上**。
