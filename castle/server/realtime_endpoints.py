# castle-voice-engine - (c) 2026 Edward / BeyondPath
# castle/server/realtime_endpoints.py - v0.1.5 OpenAI Realtime ephemeral token mint.
#
# Background:
#   v0.1.1 PersonaPlex hack confirmed unfit (model OOD on system prompt; only
#   replied "say hello" regardless of zh-TW input). v0.2 voice = OpenAI Realtime
#   API (gpt-realtime, unified speech-to-speech, $0.06/min in + $0.24/min out).
#
# This module:
#   - Loads Sophie persona prompt from castle/personas/sophie.yaml (380-word
#     mandate, zh-TW Mandarin, warm "I'm here / I get it / let me / we" tone).
#   - Exposes POST /session/token: server-side mint of an *ephemeral* Realtime
#     session token via OpenAI REST POST /v1/realtime/sessions.
#   - Returns the ephemeral client_secret so the browser can open
#     wss://api.openai.com/v1/realtime?model=gpt-realtime directly without ever
#     touching the master API key.
#
# Security:
#   - Master OPENAI_API_KEY is read only from env (Modal secret "openai").
#     It is never returned to the client. Only the ephemeral client_secret
#     (~1 min TTL) leaves the server.

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"
OPENAI_REALTIME_SESSIONS_URL = "https://api.openai.com/v1/realtime/sessions"
DEFAULT_MODEL = "gpt-realtime"
DEFAULT_VOICE = "marin"  # Edward 拍板 2026-04-28; OpenAI Realtime 2025 new voice


class TokenRequest(BaseModel):
    persona: str = "sophie"
    voice: str | None = None
    model: str | None = None


def _load_persona(name: str) -> dict[str, Any]:
    path = PERSONAS_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"persona '{name}' not registered")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _build_instructions(persona_data: dict[str, Any]) -> str:
    """Compose Realtime `instructions` from persona prompt + zh-TW hint."""
    persona = persona_data.get("persona", {}) or {}
    prompt = (persona.get("prompt") or "").strip()
    if not prompt:
        prompt = "You are Sophie, Edward's quiet, steady companion."
    # Append explicit Mandarin output hint for Realtime to stay in zh-TW.
    suffix = (
        "\n\n--- Output language ---\n"
        "Always respond in Traditional Chinese (zh-TW / Taiwan Mandarin) "
        "unless Edward explicitly switches to English. Keep replies short, "
        "conversational, and warm. Prefer 1-2 sentences over paragraphs."
    )
    return prompt + suffix


def attach_realtime_routes(app: FastAPI) -> None:
    """Attach POST /session/token onto an existing FastAPI instance."""

    @app.post("/session/token")
    async def mint_session_token(req: TokenRequest):
        raw_key = os.environ.get("OPENAI_API_KEY", "")
        # Sanitize: trim whitespace + strip leading/trailing angle brackets that
        # operators sometimes paste in from placeholder examples like <sk-proj-...>.
        master_key = raw_key.strip().strip("<>")
        if not master_key:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "openai_key_missing",
                    "detail": "OPENAI_API_KEY env var not set on Modal container",
                },
            )
        if not master_key.startswith(("sk-", "sess-")):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "openai_key_malformed",
                    "detail": (
                        "OPENAI_API_KEY does not start with sk- or sess-; "
                        "check Modal secret value for stray quotes / brackets / whitespace"
                    ),
                },
            )

        try:
            persona_data = _load_persona(req.persona)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code, content={"error": "persona_not_found", "detail": e.detail}
            )

        voice = req.voice or DEFAULT_VOICE
        model = req.model or DEFAULT_MODEL
        instructions = _build_instructions(persona_data)

        # OpenAI Realtime session config. `voice` and `instructions` here are
        # baked into the ephemeral token — the client cannot override server-side
        # persona without a fresh /session/token call.
        body = {
            "model": model,
            "voice": voice,
            "instructions": instructions,
            "modalities": ["audio", "text"],
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "gpt-4o-transcribe",  # v0.1.15: 升 newer model（比 whisper-1 準）
                "language": "zh",  # v0.1.15: 強制中文、不再 auto-detect 誤判韓文 / 日文
                "prompt": "繁體中文、台灣口音、可能混些英文 / 台語"
            },
            # Server-side VAD: OpenAI handles turn detection so the browser
            # mic doesn't have to. Edward can keep mic on the whole session.
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.8,  # v0.1.11: 從 0.7 再拉高（Edward 說 0.7 仍敏感）
                "prefix_padding_ms": 300,
                # v0.1.6.1: 從 500 → 1000ms 拉長靜音判斷、降低 echo loop 觸發
                "silence_duration_ms": 1000,
                "create_response": True,
                # v0.1.6.1: 關掉 echo barge-in（speaker 漏音不會自動 interrupt model）
                "interrupt_response": False,
            },
            "temperature": 0.8,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    OPENAI_REALTIME_SESSIONS_URL,
                    headers={
                        "Authorization": f"Bearer {master_key}",
                        "Content-Type": "application/json",
                        "OpenAI-Beta": "realtime=v1",
                    },
                    json=body,
                )
        except httpx.HTTPError as e:
            return JSONResponse(
                status_code=502,
                content={"error": "openai_unreachable", "detail": str(e)},
            )

        if resp.status_code >= 400:
            return JSONResponse(
                status_code=resp.status_code,
                content={
                    "error": "openai_session_create_failed",
                    "status": resp.status_code,
                    "detail": resp.text[:500],
                },
            )

        data = resp.json()
        client_secret = (data or {}).get("client_secret") or {}
        ephemeral_value = client_secret.get("value")
        ephemeral_expires = client_secret.get("expires_at")

        if not ephemeral_value:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "openai_no_client_secret",
                    "detail": "OpenAI response missing client_secret.value",
                    "raw_keys": list((data or {}).keys()),
                },
            )

        # Return the minimum the browser needs to open the WebSocket.
        return {
            "client_secret": ephemeral_value,
            "expires_at": ephemeral_expires,
            "model": model,
            "voice": voice,
            "persona": req.persona,
            "session_id": (data or {}).get("id"),
        }
