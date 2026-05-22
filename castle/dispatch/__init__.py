# castle-voice-engine - castle/dispatch/
# (c) 2026 Edward / BeyondPath
#
# Voice Path v2.0 Phase 2 後半段：城堡 7 同事 function calling dispatch
#
# 流程：
#   1. browser 跟 OpenAI Realtime API 連線後 fetch GET /dispatch/tools
#      拿到 7 同事 function calling schema (tools_schema.py)
#   2. browser 用 data channel session.update 把 tools 注入 OpenAI session
#   3. Edward 對 Sophie 講話、Sophie 判斷要派誰
#      → OpenAI 觸發 function_call event
#   4. browser fetch POST /dispatch + { name, arguments }
#   5. dispatch_handler 跑 Claude Haiku 模擬對應 subagent 角色 + task_log 寫 jsonl
#   6. response 回 browser → browser 用 conversation.item.create 把
#      function_call_output 注入 → Sophie 開口 narrate「霍爾跟我說 X」
#
# 為什麼這樣設計：
#   - castle-voice-engine 是純 voice engine PoC、不直接跑城堡 7 subagent
#     (那是主對話蘇菲的事 · castle-ai-system repo)
#   - 但 voice → dispatch action 的 vision 需要先 land、
#     用 Claude Haiku 模擬角色等實際接通主對話蘇菲 Hub 之前是合理 stub
#   - task_log 寫 jsonl 跨 session 持久、未來接 Hub 改成寫 Hub task queue

from castle.dispatch.castle_members import CASTLE_MEMBERS, get_member
from castle.dispatch.tools_schema import build_realtime_tools
from castle.dispatch.task_log import log_dispatch_event, recent_dispatches
from castle.dispatch.dispatch_handler import dispatch_function_call

__all__ = [
    "CASTLE_MEMBERS",
    "get_member",
    "build_realtime_tools",
    "log_dispatch_event",
    "recent_dispatches",
    "dispatch_function_call",
]
