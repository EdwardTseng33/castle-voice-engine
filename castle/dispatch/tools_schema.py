# castle-voice-engine - castle/dispatch/tools_schema.py
# (c) 2026 Edward / BeyondPath
#
# OpenAI Realtime API function calling tools schema
# Voice Path v2.0 Phase 2 後半段：讓 Sophie 語音派城堡 7 同事
#
# OpenAI Realtime tools spec reference:
#   https://platform.openai.com/docs/guides/realtime#tools
#
# 注入流程：browser 連線後 fetch GET /dispatch/tools 拿 schema、
# 用 data channel 送 session.update message 含 tools array

from __future__ import annotations

from typing import Any

from castle.dispatch.castle_members import CASTLE_MEMBERS


def build_realtime_tools() -> list[dict[str, Any]]:
    """
    Build OpenAI Realtime API tools array.

    Returns a single tool `dispatch_to_castle_member` with member key as enum.
    Single-tool design (vs 7 tools) reduces token waste in session.update
    and gives Sophie a clear mental model: 「我要派誰、派什麼事」.
    """
    member_keys = [m["key"] for m in CASTLE_MEMBERS]
    member_descriptions = "\n".join(
        f"  - {m['key']} ({m['display_name']}): {m['role']}. 派他: {m['when_to_dispatch']}"
        for m in CASTLE_MEMBERS
    )

    return [
        {
            "type": "function",
            "name": "dispatch_to_castle_member",
            "description": (
                "把任務派給城堡 7 人裡的某一位專家。Edward 講出需求、"
                "你判斷該派誰、用一句話 brief、結果會回到語音給 Edward。\n\n"
                "什麼時候用：\n"
                "  - Edward 問你「霍爾覺得呢」/「卡西法怎麼看」/「派馬魯克查一下」這類\n"
                "  - Edward 拋出明確跨領域問題、你想拉專家進來而不是 Sophie 自己答\n"
                "  - 不確定該不該派 → 不派、自己答即可 (不要無中生有派工)\n\n"
                "誰負責什麼：\n"
                f"{member_descriptions}\n\n"
                "回應風格：派完跟 Edward 一句話講「我先派 X 看 Y」、不要長解釋。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "member": {
                        "type": "string",
                        "enum": member_keys,
                        "description": "要派的城堡成員 key (英文)",
                    },
                    "brief": {
                        "type": "string",
                        "description": (
                            "給該成員的 1-2 句任務描述。用 Edward 講的話精煉、"
                            "不要加自己的判斷 (那是成員的工作)。"
                            "範例: '看 BeyondPath 這週 retention 數字、列 Top 3 異常'"
                        ),
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "對話脈絡補充 (1 句、可選)。"
                            "範例: 'Edward 剛說對 v1.0.8 退版還有疑問'"
                        ),
                    },
                },
                "required": ["member", "brief"],
            },
        },
        {
            "type": "function",
            "name": "recall_recent_dispatches",
            "description": (
                "查最近的城堡派工紀錄。Edward 問「霍爾跟我說什麼」"
                "「我剛派什麼出去了」「卡西法回了沒」時用。"
                "回最近 5 筆 (含 member / brief / 結果 / 時間)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "回幾筆 (預設 5、最多 20)",
                        "default": 5,
                    },
                    "member_filter": {
                        "type": "string",
                        "description": "只看特定成員 (可選、英文 key)",
                    },
                },
            },
        },
    ]
