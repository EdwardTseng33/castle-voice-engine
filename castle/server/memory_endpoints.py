# castle-voice-engine - castle/server/memory_endpoints.py
# (c) 2026 Edward / BeyondPath
#
# Voice Path v1.1.2 - Conversation Memory (browser IndexedDB 7 day raw / 30 day summary)
# 蘇菲跨日記憶連續性 - 開場可帶昨天 mood / promise reference
#
# 後端責任 (只摘要、不存):
#   - POST /memory/summarize - 收 browser 上傳的 raw turns -> Claude Haiku 摘要 -> 回 summary/mood/promises
#   - 後端 stateless · 不寫 Modal Volume · 不 log raw 除非 DEBUG_MEMORY=1
#   - auth gate 由 app.py middleware 自動守 (cookie 認 · 不認 401)
#   - rate limit 5 / min / cookie email (Anthropic cost 防爆)
#
# 隱私守則 (沙利曼 audit point):
#   - ANTHROPIC_API_KEY from os.environ - 沒 hardcode
#   - 不存原文 - Anthropic API call 後 response 回 client、server 不留
#   - 摘要 ≤ 80 字 - 不夾原文 - 個資（email / 手機 / 身分證 / 住址）由 prompt 排除
#   - DEBUG_MEMORY=1 才 log raw - 預設 OFF

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEBUG_RAW = os.environ.get("DEBUG_MEMORY", "0") == "1"

# Rate limit: 5 summarize / min / client (Anthropic cost 防爆)
_RATE_BUCKET: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=10))
_RATE_LIMIT_PER_MIN = 5


def _rate_ok(client_id: str) -> bool:
    now = time.time()
    bucket = _RATE_BUCKET[client_id]
    while bucket and bucket[0] < now - 60:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT_PER_MIN:
        return False
    bucket.append(now)
    return True


def _client_id(req: Request) -> str:
    # 用 cookie email 當 rate key (auth gate 已守 · 必有 email)
    # fallback IP
    try:
        from castle.server.auth_middleware import COOKIE_NAME, verify_signed_cookie
        cookie = req.cookies.get(COOKIE_NAME)
        if cookie:
            email = verify_signed_cookie(cookie)
            if email:
                return f"email::{email}"
    except Exception:
        pass
    return f"ip::{req.client.host if req.client else 'unknown'}"


class Turn(BaseModel):
    role: str = Field(..., pattern="^(user|sophie)$")
    text: str = Field(..., max_length=500)


class SummarizeReq(BaseModel):
    turns: list[Turn] = Field(default_factory=list, max_length=30)


_SYSTEM_PROMPT = (
    "你是蘇菲、Edward 的私人 AI 陪伴。"
    "把這段 Edward 跟你的對話濃縮成你自己的視角紀錄，"
    "嚴格回 JSON 物件、不要 markdown 不要 code fence："
    " summary (≤ 80 字、第一人稱『我/Edward』、不是『user/assistant』)、"
    " mood (Edward 當下心情 · enum: accomplished/stressed/tired/happy/anxious/calm/neutral)、"
    " promises (蘇菲承諾要做的事 array · 沒有就 [])。"
    "重要：不要在 summary 中提及任何個資（email / 手機 / 身分證 / 住址）。如果對話包含這些、跳過該段不摘要。"
    "範例: "
    "{\"summary\": \"Edward 跟我聊 v1.1.0 ship、看起來很累但完成了\", "
    "\"mood\": \"accomplished\", "
    "\"promises\": [\"明天提醒他喝水\"]}"
)


def _parse_json_loose(text: str) -> dict[str, Any] | None:
    """Claude 回 JSON 容錯解析 - 抓第一個 { 到最後 } 之間 · 防 markdown fence。"""
    if not text:
        return None
    # 砍 markdown fence (3 backticks · 用 chr() 避 shell expand)
    FENCE = chr(96) * 3
    text = re.sub(r"^" + FENCE + r"(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*" + FENCE + r"\s*$", "", text)
    # 抓第一個 { 到最後 }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        logger.warning("[memory] parse fail: %s", str(e)[:200])
        return None


_FALLBACK = {"summary": "", "mood": "neutral", "promises": []}


def _resolve_anthropic_key() -> str | None:
    """Modal secret env var naming 不一定是 ANTHROPIC_API_KEY · 試常見 4 名 fallback."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "anthropic_key", "ANTHROPIC"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return None


def _call_claude_haiku(turns: list[Turn]) -> dict[str, Any]:
    """Call Claude Haiku · return parsed dict or _FALLBACK on any error."""
    api_key = _resolve_anthropic_key()
    if not api_key:
        logger.warning("[memory] ANTHROPIC_API_KEY missing - returning fallback")
        return dict(_FALLBACK)

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.error("[memory] anthropic SDK not installed")
        return dict(_FALLBACK)

    transcript = "\n".join(f"{t.role}: {t.text}" for t in turns)
    if _DEBUG_RAW:
        logger.info("[memory] DEBUG raw transcript len=%d", len(transcript))

    try:
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
    except Exception as e:
        logger.warning("[memory] claude haiku call fail: %s: %s", type(e).__name__, str(e)[:200])
        return dict(_FALLBACK)

    try:
        raw_text = msg.content[0].text if msg.content else ""
    except Exception:
        return dict(_FALLBACK)

    parsed = _parse_json_loose(raw_text)
    if not parsed:
        return dict(_FALLBACK)

    # Sanitize
    summary = str(parsed.get("summary", ""))[:200]
    mood = str(parsed.get("mood", "neutral")).strip().lower()
    allowed_moods = {"accomplished", "stressed", "tired", "happy", "anxious", "calm", "neutral"}
    if mood not in allowed_moods:
        mood = "neutral"
    promises_raw = parsed.get("promises", [])
    promises: list[str] = []
    if isinstance(promises_raw, list):
        for p in promises_raw[:5]:
            if isinstance(p, str) and p.strip():
                promises.append(p.strip()[:100])
    return {"summary": summary, "mood": mood, "promises": promises}


def attach_memory_routes(app):
    """Mount memory routes onto FastAPI app.

    Routes (all auth-gated via middleware · cookie required):
        POST /memory/summarize  - turns[] -> {summary, mood, promises}
        GET  /memory/health     - simple ping
    """

    @app.get("/memory/health")
    async def _memory_health():
        return {
            "ok": True,
            "anthropic_key": bool(_resolve_anthropic_key()),
            "debug_raw": _DEBUG_RAW,
            "rate_limit_per_min": _RATE_LIMIT_PER_MIN,
        }

    @app.post("/memory/summarize")
    async def _summarize(payload: SummarizeReq, request: Request):
        # rate limit
        cid = _client_id(request)
        if not _rate_ok(cid):
            return JSONResponse(
                status_code=429,
                content={"summary": "", "mood": "neutral", "promises": [], "error": "rate_limit"},
            )

        turns = payload.turns
        if not turns or len(turns) < 2:
            return {"summary": "", "mood": "neutral", "promises": []}

        # Anthropic call
        result = _call_claude_haiku(turns)
        return result
