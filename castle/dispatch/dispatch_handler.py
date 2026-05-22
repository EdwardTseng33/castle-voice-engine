# castle-voice-engine - castle/dispatch/dispatch_handler.py
# (c) 2026 Edward / BeyondPath
#
# Function calling handler · 跑 Claude Haiku 模擬城堡同事
# Voice Path v2.0 Phase 2 後半段
#
# 為什麼用 Haiku 而不是真接 castle-ai-system 7 subagent:
#   - castle-voice-engine 是 voice engine、不該 import castle-ai-system 程式庫
#   - PoC 階段先用 Haiku 模擬 + 角色 prompt、Edward 體驗整個 voice → dispatch → 回 narrate loop
#   - 未來接 Hub task queue 取代這層、Hub 真去跑主對話蘇菲 / 7 subagent
#
# 隱私守則 (對應 security-architecture-checklist.md):
#   - 2.4 token: ANTHROPIC_API_KEY 從 Modal secret 讀、不 hardcode
#   - 4.5 output sanitization: response 不灑內部錯誤 stack trace
#   - 5.4 不主動收集: 只用 Edward 明說的 brief / context、不腦補

from __future__ import annotations

import os
import time
from typing import Any

from castle.dispatch.castle_members import get_member
from castle.dispatch.task_log import log_dispatch_event, recent_dispatches


# Claude SDK lazy import (避免 castle-voice-engine 沒 anthropic 包時整個 castle/ 炸)
_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip().strip("<>")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None
    _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def _build_member_system_prompt(member: dict[str, Any]) -> str:
    """組城堡成員的 system prompt (角色扮演)."""
    return (
        f"你是「{member['display_name']}」({member['icon']})、Edward 的城堡 7 人之一。\n"
        f"角色: {member['role']}\n"
        f"能做的事: {', '.join(member['capabilities'])}\n\n"
        "工作模式:\n"
        "- Edward 透過語音蘇菲派工給你、你回 1-3 句精煉結論給蘇菲、蘇菲再 narrate 給 Edward\n"
        "- **回應 ≤ 50 字**、講人話、不灑 markdown / bullet / heading\n"
        "- 不確定就說「我先查、晚點回」、不掰\n"
        "- 不重複 Edward 講過的話、直接給判斷 / 結論 / 下一步\n"
        "- 用台灣腔、跟 Edward 像同事說話\n"
        "- 角色相關才答、不相關直接說「這該派 X 比較對」\n\n"
        f"當前任務從蘇菲派過來、你看完直接回。"
    )


def _run_simulated_dispatch(
    member: dict[str, Any],
    brief: str,
    context: str,
) -> tuple[str, int, str]:
    """
    跑 Claude Haiku 模擬該成員角色、回 (response, latency_ms, status).

    Status: completed / failed / no_api_key
    """
    client = _get_anthropic_client()
    if client is None:
        # API key 沒設、回 stub message (PoC 仍可跑、純前後端整合測試)
        stub = (
            f"({member['display_name']} 暫時 offline · "
            "ANTHROPIC_API_KEY 沒設、PoC 模擬 stub。"
            f"任務 logged: {brief[:30]})"
        )
        return stub, 0, "no_api_key"

    system_prompt = _build_member_system_prompt(member)
    user_prompt = brief.strip()
    if context.strip():
        user_prompt += f"\n\n(背景: {context.strip()})"

    t0 = time.time()
    try:
        resp = client.messages.create(
            model=member.get("model_for_simulation", "claude-haiku-4-5"),
            max_tokens=200,  # 50 字硬限給 buffer
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:  # noqa: BLE001 - 廣捕、避免任何 anthropic SDK error 拖垮 voice loop
        latency_ms = int((time.time() - t0) * 1000)
        # 4.5 output sanitization: 不洩 stack
        err_msg = str(e)[:100]
        return f"({member['display_name']} 暫時答不出來: {err_msg})", latency_ms, "failed"
    latency_ms = int((time.time() - t0) * 1000)

    # 抽 text content
    text_parts = []
    for block in resp.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
    response = "\n".join(text_parts).strip()
    return response, latency_ms, "completed"


def dispatch_function_call(
    function_name: str,
    arguments: dict[str, Any],
    session_id: str = "",
) -> dict[str, Any]:
    """
    Main entry · OpenAI Realtime function_call → 真執行 → 結構化 response.

    Returns:
        {
            "ok": bool,
            "narrate": str,        # 給 Sophie 開口講的 1-2 句 (≤ 50 字)
            "detail": str,         # 完整 response (Sophie 不會講出來、log 用)
            "member": str,
            "latency_ms": int,
            "status": str,
        }
    """
    if function_name == "dispatch_to_castle_member":
        member_key = arguments.get("member", "").lower().strip()
        brief = arguments.get("brief", "").strip()
        context = arguments.get("context", "").strip()

        if not brief:
            return {
                "ok": False,
                "narrate": "嗯、brief 沒給、再講一次?",
                "detail": "missing brief",
                "member": member_key,
                "latency_ms": 0,
                "status": "bad_input",
            }

        member = get_member(member_key)
        if member is None:
            return {
                "ok": False,
                "narrate": f"沒這個人 ({member_key})、城堡只有 7 個。",
                "detail": f"unknown member: {member_key}",
                "member": member_key,
                "latency_ms": 0,
                "status": "bad_input",
            }

        response, latency_ms, status = _run_simulated_dispatch(member, brief, context)

        # 寫 jsonl 持久化
        log_dispatch_event(
            member=member_key,
            brief=brief,
            context=context,
            response=response,
            latency_ms=latency_ms,
            session_id=session_id,
            status=status,
        )

        # 給 Sophie narrate 的版本 (前 50 字、有頭有尾)
        narrate = response[:80].strip()
        if len(response) > 80:
            narrate = narrate.rstrip("。·、") + "..."

        return {
            "ok": status == "completed",
            "narrate": narrate,
            "detail": response,
            "member": member_key,
            "latency_ms": latency_ms,
            "status": status,
        }

    elif function_name == "recall_recent_dispatches":
        limit = int(arguments.get("limit", 5))
        if limit < 1:
            limit = 5
        if limit > 20:
            limit = 20
        member_filter = arguments.get("member_filter", "").strip() or None

        events = recent_dispatches(limit=limit, member_filter=member_filter)
        if not events:
            return {
                "ok": True,
                "narrate": "最近沒派人出去、清白。",
                "detail": "no events",
                "member": "",
                "latency_ms": 0,
                "status": "completed",
            }

        # 給 Sophie narrate 的精煉版
        lines = []
        for ev in events[:3]:  # narrate 最多講 3 件
            m = get_member(ev["member"])
            display = m["display_name"] if m else ev["member"]
            brief_short = ev["brief"][:20]
            lines.append(f"{display}: {brief_short}")
        narrate = "最近派了 " + "、".join(lines)
        if len(narrate) > 80:
            narrate = narrate[:80] + "..."

        return {
            "ok": True,
            "narrate": narrate,
            "detail": events,
            "member": "",
            "latency_ms": 0,
            "status": "completed",
        }

    return {
        "ok": False,
        "narrate": f"沒這個工具 ({function_name})",
        "detail": f"unknown function: {function_name}",
        "member": "",
        "latency_ms": 0,
        "status": "unknown_function",
    }
