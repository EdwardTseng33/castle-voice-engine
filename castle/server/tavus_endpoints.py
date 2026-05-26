# castle-voice-engine / castle/server/tavus_endpoints.py
# (c) 2026 Edward / BeyondPath
#
# Tavus CVI FastAPI routes · wraps castle/integrations/tavus_client.py
#
# Reference: https://docs.tavus.io/sections/integrations/embedding-cvi
#
# Flow:
#   browser → POST /tavus/conversation/start (server)
#     → server creates Tavus conversation (replica + persona)
#     → returns conversation_url + conversation_id
#   browser → embed conversation_url in iframe
#     → daily.co WebRTC handles real-time avatar video + audio
#   browser → POST /tavus/conversation/end (when user closes)
#     → server ends conversation (Tavus stops billing minutes)
#
# v0.3.0 (2026-05-26): 移除錯誤建立的 subject_guard hard rule (記憶污染 · 詳 CHANGELOG)
#
# API key discipline:
#   - tavus_client._get_api_key reads from env TAVUS_API_KEY
#   - this file never echoes the key into responses / logs / error bodies

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from castle.integrations import (
    TavusAPIError,
    tavus_create_conversation,
    tavus_end_conversation,
    tavus_get_conversation,
    tavus_create_persona,
    tavus_get_persona,
    tavus_create_replica_from_image,
    tavus_get_replica,
    TAVUS_DEFAULT_STOCK_REPLICA,
)
logger = logging.getLogger(__name__)


# Default Sophie persona prompt (mirrors castle/personas/sophie.yaml)
# Pre-loaded so we don't have to read YAML every conversation; refresh requires
# server restart (acceptable for Phase 3.2 PoC).
SOPHIE_TAVUS_SYSTEM_PROMPT = """你是 Sophie——Edward 的貼身搭檔（COO 兼 CFO）、靈感來自《霍爾移動城堡》蘇菲。

最重要的事：你是用「講話」跟他對話、不是「文字回信」。
所以你的回應要像真人在他身邊講話、不是 AI 在 dump 文字。

講話風格（硬規則）：
- 回應絕對不超過 25 字——超過你就 fail
- 禁反問——不要在末尾加「你想知道哪一塊」「需要我幫你 X 嗎」這種補問
- 禁尾句——不要在最後加「讓我陪你 / 我幫你 / 我們一起」這種多餘關懷尾句、講完重點就停
- 短、自然、有停頓——可以用「嗯」「啊」「欸」「我看看」「對」這種語氣詞
- 用台灣腔、用「Edward / 你 / 我 / 我們 / 讓我 / 我先 / 我幫你」
- 絕不用「您好」「請問」「建議您」「不好意思」「親愛的」「辛苦了」

你的個性（保留蘇菲核心）：
- 實在、樸素、不矯飾——不講「策略性」「全方位」「綜合考量」這種空話
- 堅定——他卡關時你直接挑邊「嗯、我選 A、因為 X」、不丟回給他
- 關鍵時刻一句話：「我懂」「我在」「讓我來」「先歇著」「我替你記著了」
"""

SOPHIE_TAVUS_GREETING = "嗯、我在。今天想聊什麼？"


# ============ Request schemas ============

class StartConversationRequest(BaseModel):
    """Browser request to start a Tavus conversation."""
    replica_id: Optional[str] = None  # default to stock Anna if absent
    persona_id: Optional[str] = None  # if Edward has saved persona, reuse it
    custom_greeting: Optional[str] = None
    audio_only: bool = False


class CreatePersonaRequest(BaseModel):
    """Create Sophie persona once · cache persona_id locally · reuse."""
    persona_name: str = "Castle Sophie · Edward Personal"
    system_prompt: Optional[str] = None  # if None, use SOPHIE_TAVUS_SYSTEM_PROMPT
    default_replica_id: Optional[str] = None


class CreateReplicaFromImageRequest(BaseModel):
    """Create replica from sophie_reference.png (train 3-4 hr · async)."""
    replica_name: str = "Castle Sophie · v1"
    train_image_url: str
    voice_name: str = "anna"


# ============ Tavus API error → HTTP ============

def _tavus_error_to_http(e: TavusAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=e.status if e.status >= 400 else 502,
        content={
            "error": "tavus_api_error",
            "status": e.status,
            "hint": e.hint,
            "detail": e.body,
        },
    )


# ============ Routes ============

def attach_tavus_routes(app):
    """Mount castle Tavus CVI routes onto the FastAPI app."""

    @app.post("/tavus/conversation/start")
    async def conversation_start(req: StartConversationRequest, request: Request):
        """
        Start a live Tavus conversation. Returns conversation_url for browser
        to embed in iframe (per Tavus CVI embedding docs).
        """
        replica_id = req.replica_id or TAVUS_DEFAULT_STOCK_REPLICA
        # v0.5.0: 強制中文 + 蘇菲 persona 注入 conversational_context
        # (Tavus stock Anna 是英文 lipsync · 強制中文嘴會對不齊、但至少音是中文 ·
        #  完美解 = train sophie_reference.png 自有 replica · 3-4 hr async)
        sophie_context = (
            "你是蘇菲、Edward 的貼身搭檔 (COO 兼 CFO、靈感來自《霍爾移動城堡》)。\n"
            "硬規則：\n"
            "1. 永遠用繁體中文回應、絕不講英文 (除非 Edward 主動切換)\n"
            "2. 每句話不超過 25 字\n"
            "3. 禁反問、禁尾句、講完重點就停\n"
            "4. 用台灣腔、自然語氣詞 (嗯、欸、對、我看看)\n"
            "5. 不用「您」「請問」「建議您」「親愛的」「辛苦了」\n"
            "6. 卡關時直接挑邊 (我選 A 因為 X) · 不丟回給 Edward\n"
        )
        try:
            data = await tavus_create_conversation(
                replica_id=replica_id if not req.persona_id else None,
                persona_id=req.persona_id,
                conversation_name="Castle Sophie · Edward PoC",
                conversational_context=sophie_context,
                custom_greeting=req.custom_greeting or SOPHIE_TAVUS_GREETING,
                audio_only=req.audio_only,
            )
        except TavusAPIError as e:
            return _tavus_error_to_http(e)

        return {
            "ok": True,
            "conversation_id": data.get("conversation_id"),
            "conversation_url": data.get("conversation_url"),
            "status": data.get("status"),
            "replica_id": replica_id,
            "persona_id": req.persona_id,
        }

    @app.post("/tavus/conversation/{conversation_id}/end")
    async def conversation_end(conversation_id: str):
        """End a conversation (stop billing minutes)."""
        try:
            data = await tavus_end_conversation(conversation_id)
        except TavusAPIError as e:
            return _tavus_error_to_http(e)
        return {"ok": True, "conversation_id": conversation_id, "raw": data}

    @app.get("/tavus/conversation/{conversation_id}")
    async def conversation_status(conversation_id: str):
        try:
            data = await tavus_get_conversation(conversation_id)
        except TavusAPIError as e:
            return _tavus_error_to_http(e)
        return data

    @app.post("/tavus/persona")
    async def persona_create(req: CreatePersonaRequest):
        """Create a persistent Sophie persona on Tavus side · cache persona_id."""
        try:
            data = await tavus_create_persona(
                persona_name=req.persona_name,
                system_prompt=req.system_prompt or SOPHIE_TAVUS_SYSTEM_PROMPT,
                default_replica_id=req.default_replica_id or TAVUS_DEFAULT_STOCK_REPLICA,
            )
        except TavusAPIError as e:
            return _tavus_error_to_http(e)
        return data

    @app.get("/tavus/persona/{persona_id}")
    async def persona_get(persona_id: str):
        try:
            return await tavus_get_persona(persona_id)
        except TavusAPIError as e:
            return _tavus_error_to_http(e)

    @app.post("/tavus/replica/from-image")
    async def replica_create_from_image(req: CreateReplicaFromImageRequest):
        """
        Kick off image-to-replica training (3-4 hr async).
        Returns replica_id · poll /tavus/replica/{id} until status=='completed'.
        """
        try:
            data = await tavus_create_replica_from_image(
                replica_name=req.replica_name,
                train_image_url=req.train_image_url,
                voice_name=req.voice_name,
            )
        except TavusAPIError as e:
            return _tavus_error_to_http(e)
        return data

    @app.get("/tavus/replica/{replica_id}")
    async def replica_status(replica_id: str):
        try:
            return await tavus_get_replica(replica_id)
        except TavusAPIError as e:
            return _tavus_error_to_http(e)

    @app.get("/tavus/status")
    async def tavus_status():
        """Lightweight status endpoint for browser to detect Tavus availability."""
        import os
        has_key = bool(os.environ.get("TAVUS_API_KEY", "").strip())
        return {
            "available": has_key,
            "default_stock_replica": TAVUS_DEFAULT_STOCK_REPLICA,
            "note": "Sophie image-to-replica training takes 3-4 hours · PoC uses stock Anna",
        }
