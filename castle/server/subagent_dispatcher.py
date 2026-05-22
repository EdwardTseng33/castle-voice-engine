# castle-voice-engine - v0.3.0 Phase 2 (Path B)
# castle/server/subagent_dispatcher.py
#
# Bridges OpenAI Realtime function calls -> Anthropic Claude calls into castle
# subagent prompts.
#
# Edward speaks (Mandarin) -> gpt-realtime-2 -> emits function_call event ->
# browser forwards to POST /dispatch -> this module loads the corresponding
# subagent system prompt (turnip / calcifer / howl) -> calls Anthropic Messages
# API -> returns plain-text result -> browser injects result back to OpenAI via
# conversation.item.create + response.create.
#
# Why not call from browser directly: Anthropic key must stay server-side, and
# subagent prompts are big enough (~10-15k tokens each) that we don't want to
# round-trip them via the data channel.
#
# Why only 3 subagents in Phase 2 (not all 7): turnip/calcifer/howl cover the
# three most common voice query patterns (user research / tech / strategy).
# Adding markl/sophie/suliman/witch is mechanical once the dispatcher pattern
# works; staged on purpose.

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

SUBAGENTS_DIR = Path(__file__).resolve().parent.parent / "subagents"

# Phase 2 subagents (3 of 7). When expanding, add to this dict + tools spec in
# realtime_endpoints._SUBAGENT_TOOLS.
_REGISTRY = {
    "turnip": {
        "file": "turnip.md",
        "display": "蕪菁頭 (用戶研究)",
        "description": "用戶意圖 / 行為分析 / persona 設計 / 用戶 metric。問用戶在想什麼、為什麼留下 / 離開、retention / dispatch 數據時找他。",
    },
    "calcifer": {
        "file": "calcifer.md",
        "display": "卡西法 (CTO / 技術)",
        "description": "技術架構 / 程式碼 / Bug 修復 / debug / Agent 串接 / 自動化 / 估時 / Chrome MCP 實測。技術可行性 / 怎麼做 / 多久 / 哪裡壞 找他。",
    },
    "howl": {
        "file": "howl.md",
        "display": "霍爾 (CPO / 策略)",
        "description": "產品策略 / 競品分析 / 品牌 / 商業判斷 / 取捨。值不值得做 / 對手在幹嘛 / 品牌定位 找他。",
    },
}

_DEFAULT_MODEL = "claude-sonnet-4-5"  # cheap+fast; bumps to opus 4.x if Edward asks for深度

# Cache loaded prompts so we don't re-read disk on every dispatch.
_PROMPT_CACHE: dict[str, str] = {}


def _load_subagent_prompt(name: str) -> str:
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    if name not in _REGISTRY:
        raise ValueError(f"unknown subagent: {name}")
    path = SUBAGENTS_DIR / _REGISTRY[name]["file"]
    if not path.exists():
        raise FileNotFoundError(f"subagent prompt missing at {path}")
    with path.open("r", encoding="utf-8") as fh:
        text = fh.read()
    _PROMPT_CACHE[name] = text
    return text


def list_subagents() -> list[dict]:
    """Return descriptive list for /subagents endpoint."""
    return [{"name": k, "display": v["display"], "description": v["description"]} for k, v in _REGISTRY.items()]


def get_subagent_tools_spec() -> list[dict]:
    """OpenAI Realtime function-tool spec (subset used in session.update.tools).

    Format follows OpenAI Realtime API function tool schema:
      { type: 'function', name: '...', description: '...', parameters: {...} }
    """
    tools = []
    for name, meta in _REGISTRY.items():
        tools.append({
            "type": "function",
            "name": f"call_{name}",
            "description": meta["description"],
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": f"問 {meta['display']} 的問題、用 Edward 的原話、不要重新組織",
                    },
                    "context": {
                        "type": "string",
                        "description": "(optional) 額外上下文、補充背景",
                    },
                },
                "required": ["question"],
            },
        })
    return tools


async def dispatch_to_subagent(name: str, question: str, context: Optional[str] = None) -> dict:
    """Call Anthropic Claude with the given subagent's system prompt.

    Returns dict { ok: bool, subagent: str, text: str, model: str, error?: str }.

    Designed to NEVER raise: we always return a dict so the dispatcher endpoint
    can pipe errors back to the browser, which then injects them into OpenAI as
    a system message ("subagent X failed, here is what happened...") so the
    voice loop never hangs.
    """
    if name not in _REGISTRY:
        return {"ok": False, "subagent": name, "text": "", "model": "", "error": f"unknown subagent: {name}"}

    api_key = (os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_KEY", "")).strip().strip("<>")
    if not api_key:
        return {"ok": False, "subagent": name, "text": "", "model": "", "error": "ANTHROPIC_API_KEY not set on server (Modal secret 'anthropic-key' not loaded)"}
    if not api_key.startswith("sk-ant-"):
        return {"ok": False, "subagent": name, "text": "", "model": "", "error": "ANTHROPIC_API_KEY malformed (does not start with sk-ant-)"}

    try:
        system_prompt = _load_subagent_prompt(name)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "subagent": name, "text": "", "model": "", "error": f"failed to load prompt: {e}"}

    # Build the user message. We keep voice-replies short — Edward is speaking,
    # not reading. So we cap max_tokens low and prepend a voice-mode hint.
    user_msg_parts = [
        "[Edward 正在用語音跟蘇菲對話、蘇菲把問題派給你。回答要短、像在講話、不要 markdown 不要列點。最好 < 80 字、講重點就好、需要時可分 2-3 句。]",
        "",
        "問題：" + question.strip(),
    ]
    if context:
        user_msg_parts.append("")
        user_msg_parts.append("補充：" + context.strip())
    user_msg = "\n".join(user_msg_parts)

    try:
        import anthropic  # noqa: PLC0415
    except ImportError:
        return {"ok": False, "subagent": name, "text": "", "model": "", "error": "anthropic SDK not installed on server (requirements.txt missing 'anthropic')"}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        # Use sync .messages.create inside async — Modal already runs each
        # request on its own thread + we don't want to pull anthropic async
        # client just for this; latency dominated by Claude API anyway (1-3s).
        import asyncio  # noqa: PLC0415
        loop = asyncio.get_running_loop()

        def _call():
            return client.messages.create(
                model=_DEFAULT_MODEL,
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )

        resp = await loop.run_in_executor(None, _call)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "subagent": name, "text": "", "model": _DEFAULT_MODEL, "error": f"anthropic API error: {type(e).__name__}: {e}"}

    # Extract plain text from response. Anthropic returns content blocks list.
    text_chunks = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", "") == "text":
            text_chunks.append(getattr(block, "text", ""))
    text = "\n".join(t for t in text_chunks if t).strip()
    if not text:
        text = "(空回應 · subagent 沒給內容)"

    return {"ok": True, "subagent": name, "text": text, "model": _DEFAULT_MODEL, "error": None}
