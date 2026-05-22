# castle-voice-engine / castle/integrations/tavus_client.py
# (c) 2026 Edward / BeyondPath
#
# Tavus Conversational Video Interface (CVI) REST API thin wrapper.
#
# Reference (Tavus official docs · fetched 2026-05-23):
#   - https://docs.tavus.io/api-reference/personas/create-persona
#   - https://docs.tavus.io/api-reference/phoenix-replica-model/create-replica
#   - https://docs.tavus.io/api-reference/conversations/create-conversation
#   - https://docs.tavus.io/sections/replica/image-to-replica-quickstart
#   - https://docs.tavus.io/sections/integrations/embedding-cvi
#
# Three core concepts:
#   1. Replica = digital face clone (Phoenix-4 model · stock or image-trained)
#   2. Persona = system_prompt + LLM/TTS/STT pipeline + default_replica_id
#   3. Conversation = live session (returns conversation_url for browser join)
#
# Image-to-replica training takes 3-4 hours · PoC uses stock Anna replica while
# we kick off background train of Edward-chosen sophie_reference.png in parallel.
#
# Discipline:
#   - API key read from env (TAVUS_API_KEY) · never hardcoded · never logged
#   - Sally hard rule enforced by callers (subject_guard.enforce_subject_whitelist)
#   - All async (httpx.AsyncClient) · does not block FastAPI loop
#   - No official Python SDK exists; this is the thin idiomatic wrapper
#
# Vendor abstraction note:
#   If Anam audit (sulima #6) verdicts swap, copy this file to anam_client.py
#   with the same interface (create_persona / create_replica / create_conversation).
#   The endpoints / browser layer should not need to change.

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# === Constants pinned from Tavus docs 2026-05-23 ===
TAVUS_API_BASE = "https://tavusapi.com/v2"
TAVUS_API_KEY_ENV = "TAVUS_API_KEY"

# Stock replicas (Phoenix-4 Pro · from /sections/replica/stock-replicas)
STOCK_REPLICA_ANNA = "r90bbd427f71"      # female · Sophie stand-in for PoC
STOCK_REPLICA_GLORIA = "r5dc7c7d0bcb"
STOCK_REPLICA_LUCAS = "r874cc5f8a3b"
DEFAULT_STOCK_REPLICA = STOCK_REPLICA_ANNA

PIPELINE_FULL = "full"
PIPELINE_ECHO = "echo"

HTTP_TIMEOUT_QUICK = 15.0
HTTP_TIMEOUT_TRAIN = 30.0


class TavusAPIError(Exception):
    """Tavus REST call failed · status==0 means transport / config error."""

    def __init__(self, status: int, body: str = "", hint: str = ""):
        self.status = status
        self.body = (body or "")[:500]
        self.hint = hint
        super().__init__(f"Tavus API {status}: {self.body} · {hint}")


def _get_api_key() -> str:
    key = os.environ.get(TAVUS_API_KEY_ENV, "").strip()
    if not key:
        raise TavusAPIError(
            status=0,
            hint=f"missing env var {TAVUS_API_KEY_ENV} · set in Modal secret tavus or .env",
        )
    return key


def _headers() -> dict[str, str]:
    # Caller MUST NOT log this dict (contains api key).
    return {"Content-Type": "application/json", "x-api-key": _get_api_key()}


async def _post(path: str, body: dict[str, Any], timeout: float = HTTP_TIMEOUT_QUICK) -> dict[str, Any]:
    url = f"{TAVUS_API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=_headers())
    except httpx.RequestError as e:
        raise TavusAPIError(status=0, body=str(e), hint=f"transport error POST {path}") from e

    if resp.status_code >= 400:
        logger.warning("Tavus POST %s status=%d body=%s", path, resp.status_code, resp.text[:200])
        raise TavusAPIError(status=resp.status_code, body=resp.text, hint=f"POST {path} failed")
    return resp.json()


async def _get(path: str, timeout: float = HTTP_TIMEOUT_QUICK) -> dict[str, Any]:
    url = f"{TAVUS_API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=_headers())
    except httpx.RequestError as e:
        raise TavusAPIError(status=0, body=str(e), hint=f"transport error GET {path}") from e

    if resp.status_code >= 400:
        logger.warning("Tavus GET %s status=%d body=%s", path, resp.status_code, resp.text[:200])
        raise TavusAPIError(status=resp.status_code, body=resp.text, hint=f"GET {path} failed")
    return resp.json()


# ====== Persona ======

async def create_persona(
    persona_name: str,
    system_prompt: str,
    *,
    default_replica_id: str = DEFAULT_STOCK_REPLICA,
    pipeline_mode: str = PIPELINE_FULL,
    context: Optional[str] = None,
    layers: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "persona_name": persona_name,
        "system_prompt": system_prompt,
        "pipeline_mode": pipeline_mode,
        "default_replica_id": default_replica_id,
    }
    if context:
        body["context"] = context
    if layers:
        body["layers"] = layers
    return await _post("/personas", body)


async def get_persona(persona_id: str) -> dict[str, Any]:
    return await _get(f"/personas/{persona_id}")


# ====== Replica (image-to-replica · async train · 3-4 hr) ======

async def create_replica_from_image(
    replica_name: str,
    train_image_url: str,
    voice_name: str = "anna",
    *,
    callback_url: str = "",
    auto_fix_training_image: bool = True,
) -> dict[str, Any]:
    body = {
        "callback_url": callback_url,
        "replica_name": replica_name,
        "train_image_url": train_image_url,
        "voice_name": voice_name,
        "auto_fix_training_image": auto_fix_training_image,
    }
    return await _post("/replicas", body, timeout=HTTP_TIMEOUT_TRAIN)


async def get_replica(replica_id: str) -> dict[str, Any]:
    return await _get(f"/replicas/{replica_id}")


# ====== Conversation (live · returns conversation_url for browser join) ======

async def create_conversation(
    *,
    replica_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    conversation_name: str = "Castle Sophie",
    participant_name: str = "Edward",  # 預設 · 跳過 Daily prejoin "Enter your name" friction
    conversational_context: Optional[str] = None,
    custom_greeting: Optional[str] = None,
    audio_only: bool = False,
    callback_url: str = "",
    properties: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not replica_id and not persona_id:
        raise TavusAPIError(
            status=0,
            hint="create_conversation requires replica_id or persona_id (per Tavus docs)",
        )
    body: dict[str, Any] = {
        "conversation_name": conversation_name,
        "participant_name": participant_name,  # 跳過 prejoin
    }
    if replica_id:
        body["replica_id"] = replica_id
    if persona_id:
        body["persona_id"] = persona_id
    if conversational_context:
        body["conversational_context"] = conversational_context
    if custom_greeting:
        body["custom_greeting"] = custom_greeting
    if audio_only:
        body["audio_only"] = True
    if callback_url:
        body["callback_url"] = callback_url
    # properties: 額外 Daily.co iframe 控制 (enable_recording / language / etc)
    if properties:
        body["properties"] = properties
    return await _post("/conversations", body)


async def get_conversation(conversation_id: str) -> dict[str, Any]:
    return await _get(f"/conversations/{conversation_id}")


async def end_conversation(conversation_id: str) -> dict[str, Any]:
    return await _post(f"/conversations/{conversation_id}/end", {})
