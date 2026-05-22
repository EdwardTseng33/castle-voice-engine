# castle-voice-engine - castle/server/dispatch_endpoints.py
# (c) 2026 Edward / BeyondPath
#
# FastAPI endpoints · OpenAI Realtime function calling backend
# Voice Path v2.0 Phase 2 後半段
#
# 流程：
#   browser ↔ OpenAI WebRTC direct
#     ↓ function_call event
#   browser → POST /dispatch → castle-voice-engine
#     ↓ dispatch_handler.dispatch_function_call
#   castle-voice-engine → Claude Haiku 模擬城堡同事
#     ↓ response
#   browser ← {narrate, detail} ← castle-voice-engine
#     ↓ conversation.item.create function_call_output
#   browser → OpenAI Realtime session
#     ↓ Sophie speaks narrate
#
# 隱私守則 (對應 security-architecture-checklist.md):
#   - 4.1 rate limiting: 預設 30 dispatch / min / IP (in-memory bucket)
#   - 4.3 authorization: 沒 auth header 也 OK (PoC dev mode)、prod 加 token
#   - 4.7 error message 不洩內部 detail (4.5 已在 dispatch_handler 做)
#   - 5.1 opt-in: GET /dispatch/tools 任何人可讀 (是 schema 不是資料)
#                POST /dispatch 才碰 Edward 對話內容

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from castle.dispatch import build_realtime_tools, dispatch_function_call, recent_dispatches
from castle.integrations import is_speechbrain_ready, is_spacy_ready


# 簡單 in-memory rate limit (PoC 等級 · prod 該用 Redis / Modal Volume)
_RATE_BUCKET: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=60))
_RATE_LIMIT_PER_MIN = 30


def _rate_limit_ok(client_id: str) -> bool:
    now = time.time()
    bucket = _RATE_BUCKET[client_id]
    # 把 60 秒以前的 timestamp 拋掉
    while bucket and bucket[0] < now - 60:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT_PER_MIN:
        return False
    bucket.append(now)
    return True


def _client_id_from_request(req: Request) -> str:
    """用 IP + UA 當 rate limit key (PoC · 不精準但夠用)."""
    ip = req.client.host if req.client else "unknown"
    ua = req.headers.get("user-agent", "")[:50]
    return f"{ip}::{ua}"


class DispatchRequest(BaseModel):
    function_name: str
    arguments: dict[str, Any]
    session_id: str = ""


def attach_dispatch_routes(app):
    """Mount castle dispatch endpoints onto the FastAPI app."""

    @app.get("/dispatch/tools")
    async def get_tools():
        """
        Browser fetch this on Realtime connection open、
        inject 結果用 data channel session.update 送進 OpenAI。

        Returns:
            { "tools": [...OpenAI Realtime tools schema...] }
        """
        return {"tools": build_realtime_tools()}

    @app.post("/dispatch")
    async def execute_dispatch(payload: DispatchRequest, request: Request):
        """
        Browser 收到 OpenAI function_call event → 轉發來這、
        我們跑 Claude Haiku 模擬城堡同事 → 回 narrate + detail。
        """
        client_id = _client_id_from_request(request)
        if not _rate_limit_ok(client_id):
            return JSONResponse(
                status_code=429,
                content={
                    "ok": False,
                    "error": "rate_limit",
                    "narrate": "派太頻繁了、等一下下。",
                    "detail": f"limit {_RATE_LIMIT_PER_MIN} dispatches per minute",
                },
            )

        result = dispatch_function_call(
            function_name=payload.function_name,
            arguments=payload.arguments,
            session_id=payload.session_id,
        )
        return result

    @app.get("/dispatch/recent")
    async def list_recent(limit: int = 10, member: str | None = None):
        """
        Dev / debug · 看最近派工紀錄。
        Prod 可關掉 (return 401) 或加 auth。
        """
        if limit < 1 or limit > 50:
            limit = 10
        return {
            "events": recent_dispatches(limit=limit, member_filter=member),
            "count": min(limit, 50),
        }

    @app.get("/phase2/status")
    async def phase2_status():
        """
        Edward 用瀏覽器打開、看 Phase 2 後半段 3 件功能 ready 沒。

        2026-05-22 update:
          - Picovoice 改企業版 only、本系統改用 SpeechBrain (聲紋) + OpenAI VAD (喚醒)
          - Edward 不必動任何網站 / 鑰匙 / 註冊
        """
        sb = is_speechbrain_ready()
        spacy_status = is_spacy_ready()
        return {
            "phase2_back_half": {
                "castle_dispatch": {
                    "ready": True,
                    "tools_count": len(build_realtime_tools()),
                    "hint": "✅ 城堡 7 同事派工已上線、Sophie 講話可派霍爾 / 卡西法 / 馬魯克等",
                },
                "voice_id_speechbrain": {
                    "ready": sb["enrolled_embedding_exists"] and sb["speechbrain_installed"],
                    "torch_installed": sb["torch_installed"],
                    "speechbrain_installed": sb["speechbrain_installed"],
                    "voice_sample_exists": sb["voice_sample_exists"],
                    "enrolled": sb["enrolled_embedding_exists"],
                    "model_cached": sb["model_cached"],
                    "hint": (
                        "✅"
                        if (sb["enrolled_embedding_exists"] and sb["speechbrain_installed"])
                        else "蘇菲跑 pip install + 用 Edward 4/28 m4a 註冊、Edward 不必動"
                    ),
                },
                "pii_redaction_spacy": {
                    "ready": spacy_status["model_loaded"],
                    "spacy_installed": spacy_status["spacy_installed"],
                    "model_loaded": spacy_status["model_loaded"],
                    "hint": (
                        "✅"
                        if spacy_status["model_loaded"]
                        else "Edward 回「跑」、蘇菲裝 (`python -m spacy download zh_core_web_sm`)"
                    ),
                },
            },
            "deprecated": {
                "picovoice": "2026-05-22 改企業版 only、castle 改 SpeechBrain + OpenAI VAD",
            },
            "edward_action_required": False,  # SpeechBrain + OpenAI VAD 都自動、不必註冊
        }
