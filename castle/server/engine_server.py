# castle-voice-engine — Copyright (c) 2026 Edward / BeyondPath
# Built on PersonaPlex (NVIDIA, NOML) and Moshi (Kyutai, MIT)
# castle/server/engine_server.py
# FastAPI + WebSocket wrapper around Moshi server with persona registry + auth.

from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from castle import wire_protocol as wp

PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"
AUTH_TOKEN = os.environ.get("CVE_AUTH_TOKEN")  # required in prod; mock-bypass if unset

app = FastAPI(title="castle-voice-engine", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before prod
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-process single-tenant lock (PersonaPlex requirement: one session per server).
_engine_lock = asyncio.Lock()

def load_persona(name: str) -> dict[str, Any]:
    path = PERSONAS_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"persona '{name}' not registered")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}

def check_auth(token: Optional[str]) -> None:
    if AUTH_TOKEN is None:
        return  # dev mode — no auth
    if not token or not secrets.compare_digest(token, AUTH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid auth token")

@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "engine": "castle-voice-engine", "version": "0.2.0", "model_default": "gpt-realtime-2", "licence": "NOML"}

@app.get("/personas")
async def list_personas() -> dict[str, Any]:
    return {"personas": [p.stem for p in PERSONAS_DIR.glob("*.yaml")]}

@app.websocket("/voice")
async def voice_ws(
    websocket: WebSocket,
    persona: str = Query(default="sophie"),
    token: Optional[str] = Query(default=None),
    x_cve_token: Optional[str] = Header(default=None, alias="X-CVE-Token"),
) -> None:
    # auth: header preferred, query fallback
    try:
        check_auth(x_cve_token or token)
    except HTTPException as e:
        await websocket.close(code=4401, reason=e.detail)
        return

    persona_data = load_persona(persona)
    voice_preset = wp.resolve_voice_preset(persona_data)

    # PersonaPlex needs a single-session lock — refuse if engine is busy
    if _engine_lock.locked():
        await websocket.close(code=4409, reason="engine busy")
        return

    await websocket.accept()
    session_id = secrets.token_urlsafe(12)
    await websocket.send_text(wp.connected(session_id, persona_data["name"], voice_preset))

    async with _engine_lock:
        try:
            await _run_session(websocket, persona_data)
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            try:
                await websocket.send_text(wp.error(f"engine error: {e}"))
            finally:
                await websocket.close(code=1011, reason="engine error")

async def _run_session(ws: WebSocket, persona_data: dict[str, Any]) -> None:
    # TODO(plug-in-moshi): replace this stub loop with actual Moshi tokenisation +
    # PersonaPlex inference + Opus encoding pipeline.
    # For now we just echo a state cycle so the client can be wired end-to-end.
    await ws.send_text(wp.state_change("idle", "listening"))
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            return
        text_payload = message.get("text")
        bytes_payload = message.get("bytes")
        if text_payload is not None:
            inbound = wp.parse_inbound(text_payload)
            if inbound.type == "goodbye":
                return
            if inbound.type == "switch_persona":
                persona_data = load_persona(inbound.data.get("persona", persona_data["name"]))
                await ws.send_text(wp.state_change("any", f"persona_switched:{persona_data['name']}"))
            elif inbound.type in ("hello", "user_text"):
                # canned demo cycle until Moshi is wired
                await _emit_demo_reply(ws)
        elif bytes_payload is not None:
            # raw mic chunk — TODO: decode Opus + feed to Moshi
            await ws.send_text(wp.partial_transcript(f"(received {len(bytes_payload)}B)", source="user"))

async def _emit_demo_reply(ws: WebSocket) -> None:
    await ws.send_text(wp.state_change("listening", "speaking"))
    for sentence in ("我聽到你說的問題了。", "讓我想想下一步⋯", "先從 persona 定位開始好嗎？"):
        await ws.send_text(wp.partial_transcript(sentence, source="agent"))
        await asyncio.sleep(0.4)
    await ws.send_text(wp.final_transcript("我聽到你說的問題了。讓我想想下一步⋯ 先從 persona 定位開始好嗎？", source="agent"))
    await ws.send_text(wp.state_change("speaking", "idle"))
