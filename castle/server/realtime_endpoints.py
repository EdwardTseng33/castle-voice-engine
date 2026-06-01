# castle-voice-engine - v0.2.3 GA Realtime API (calls endpoint)
# (c) 2026 Edward / BeyondPath
# castle/server/realtime_endpoints.py
#
# v0.2.2 -> v0.2.3 (2026-05-22 hotfix #2 after Edward demo deprecation 400):
#   - GA SDP exchange endpoint is /v1/realtime/calls (not /v1/realtime).
#   - /v1/realtime is WebSocket-only; POSTing SDP there triggers OpenAI
#     'Realtime Beta API no longer supported' 400 even though the URL itself
#     pre-dates the GA cutover.
#   - Single-line change: OPENAI_REALTIME_URL -> /v1/realtime/calls.
#   - /session/token still 410 Gone (unchanged from v0.2.1).
#
# v0.2.0 -> v0.2.1 (2026-05-22 first hotfix):
#   - OpenAI GA: Beta /v1/realtime/sessions deprecated 5/8.
#   - /sdp bypasses ephemeral token mint, forwards SDP to OpenAI directly.
#   - /session/token returns 410 Gone (deprecation notice).

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote as urlquote

import base64
import json

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from castle.dispatch import build_realtime_tools
from castle.server.persona_director import build_director_contract, decide_persona_state

PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"
OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime/calls"

DEFAULT_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2").strip() or "gpt-realtime-2"
FALLBACK_MODEL = "gpt-realtime"
DEFAULT_VOICE = "marin"
_VALID_VOICES = {"alloy", "ash", "ballad", "coral", "echo", "marin", "nova", "sage", "shimmer", "verse", "cedar"}


class TokenRequest(BaseModel):
    persona: str = "sophie"
    voice: str | None = None
    model: str | None = None


class DirectorRequest(BaseModel):
    transcript: str | None = None
    last_user_text: str | None = None
    requested_mode: str | None = None
    conversation_state: str | None = None
    user_visible: bool | None = None
    camera_enabled: bool | None = None
    seconds_since_user_audio: float | None = None
    desktop_context: dict | None = None
    risk_flags: list[str] | None = None
    is_external_action: bool = False
    is_tool_wait: bool = False


def _load_persona(name):
    path = PERSONAS_DIR / (name + ".yaml")
    if not path.exists():
        raise HTTPException(status_code=404, detail="persona not registered")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _build_instructions(persona_data):
    persona = persona_data.get("persona", {}) or {}
    prompt = (persona.get("prompt") or "").strip()
    if not prompt:
        prompt = "You are an attentive companion."
    lang = (persona_data.get("language") or "zh-TW").strip().lower()
    if lang.startswith("en"):
        suffix = "\n\n--- Output language ---\nAlways respond in English. Keep replies short, conversational, and warm."
    else:
        suffix = "\n\n--- Output language ---\nAlways respond in Traditional Chinese (zh-TW / Taiwan Mandarin) unless Edward explicitly switches to English. Keep replies short, conversational, and warm."
    return prompt + suffix + build_director_contract()


def _resolve_voice(persona_data, requested_voice):
    persona_voice = ((persona_data.get("voice") or {}).get("preset_id") or "").strip()
    if persona_voice not in _VALID_VOICES:
        persona_voice = ""
    return requested_voice or persona_voice or DEFAULT_VOICE


def _sanitize_master_key():
    raw_key = os.environ.get("OPENAI_API_KEY", "")
    master_key = raw_key.strip().strip("<>")
    if not master_key:
        return None, JSONResponse(status_code=503, content={"error": "openai_key_missing", "detail": "OPENAI_API_KEY env var not set"})
    if not master_key.startswith(("sk-", "sess-")):
        return None, JSONResponse(status_code=503, content={"error": "openai_key_malformed", "detail": "OPENAI_API_KEY does not start with sk- or sess-"})
    return master_key, None


async def _post_sdp_to_openai(master_key, model, voice, instructions, sdp_offer):
    qs = "?model=" + urlquote(model)
    if voice:
        qs += "&voice=" + urlquote(voice)
    url = OPENAI_REALTIME_URL + qs
    headers = {
        "Authorization": "Bearer " + master_key,
        "Content-Type": "application/sdp",
    }
    # v0.2.2: instructions are NOT forwarded to OpenAI here; the browser
    # injects them via data channel session.update on connection open. We just
    # need to ensure the SDP exchange works; persona prompt is bundled into the
    # response headers so the browser can use it.
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, content=sdp_offer)
    except httpx.HTTPError as e:
        return None, 502, "openai unreachable: " + str(e)
    if resp.status_code >= 400:
        return None, resp.status_code, resp.text
    return resp.text, resp.status_code, None


def _looks_like_model_not_found(status, text):
    if status not in (400, 404):
        return False
    needle = (text or "").lower()
    return ("model_not_found" in needle) or ("does not exist" in needle) or ("invalid model" in needle) or ("unknown model" in needle)


def attach_realtime_routes(app):
    @app.post("/session/token")
    async def session_token_gone(req: TokenRequest):
        return JSONResponse(
            status_code=410,
            content={
                "error": "session_token_endpoint_removed",
                "detail": "OpenAI Realtime Beta API (/v1/realtime/sessions) was deprecated on 2026-05-08; GA SDP endpoint is /v1/realtime/calls. Use POST /sdp on this server with a WebRTC SDP offer.",
                "upgrade_path": "POST /sdp?persona=sophie&model=gpt-realtime-2 with body = WebRTC SDP offer (Content-Type: application/sdp); this server forwards to OpenAI /v1/realtime/calls.",
            },
        )

    @app.post("/sdp")
    async def exchange_sdp(request: Request):
        master_key, err = _sanitize_master_key()
        if err is not None:
            return err
        persona_name = request.query_params.get("persona", "sophie")
        voice_q = request.query_params.get("voice", "") or ""
        req_model = (request.query_params.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        try:
            persona_data = _load_persona(persona_name)
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"error": "persona_not_found", "detail": e.detail})
        sdp_offer = (await request.body()).decode("utf-8", errors="replace")
        if not sdp_offer.startswith("v=0"):
            return JSONResponse(status_code=400, content={"error": "bad_sdp_offer", "detail": "body must be a raw SDP offer (text/plain)"})
        voice = _resolve_voice(persona_data, voice_q)
        instructions = _build_instructions(persona_data)
        answer, status, err_text = await _post_sdp_to_openai(master_key, req_model, voice, instructions, sdp_offer)
        used_model = req_model
        warning = None
        if answer is None and _looks_like_model_not_found(status, err_text) and req_model != FALLBACK_MODEL:
            answer2, status2, err_text2 = await _post_sdp_to_openai(master_key, FALLBACK_MODEL, voice, instructions, sdp_offer)
            if answer2 is not None:
                answer = answer2
                used_model = FALLBACK_MODEL
                warning = "primary_model_unavailable_used_fallback:" + req_model
            else:
                return JSONResponse(status_code=status2, content={"error": "openai_sdp_exchange_failed_both", "primary_status": status, "primary_detail": (err_text or "")[:500], "fallback_status": status2, "fallback_detail": (err_text2 or "")[:500], "primary_model": req_model, "fallback_model": FALLBACK_MODEL})
        if answer is None:
            return JSONResponse(status_code=status, content={"error": "openai_sdp_exchange_failed", "status": status, "detail": (err_text or "")[:500], "model_tried": used_model})
        instr_b64 = base64.b64encode(instructions.encode("utf-8")).decode("ascii")
        # v0.3.0 Phase 2 後半段: tools schema 一起塞 header 給 browser
        # browser 連線後從 header 拿 tools (or fallback fetch GET /dispatch/tools)
        # 再用 data channel session.update 注入 OpenAI Realtime session
        tools = build_realtime_tools()
        tools_json = json.dumps(tools, ensure_ascii=False)
        tools_b64 = base64.b64encode(tools_json.encode("utf-8")).decode("ascii")
        headers = {
            "x-realtime-model": used_model,
            "x-realtime-voice": voice,
            "x-realtime-persona": persona_name,
            "x-realtime-instructions-b64": instr_b64,
            "x-realtime-tools-b64": tools_b64,
            "x-realtime-tools-count": str(len(tools)),
        }
        if warning:
            headers["x-realtime-warning"] = warning
            headers["x-realtime-fallback-from"] = req_model
        return PlainTextResponse(content=answer, media_type="application/sdp", headers=headers)

    @app.post("/director/decide")
    async def director_decide(req: DirectorRequest):
        payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        decision = decide_persona_state(payload)
        return JSONResponse(content=decision.to_dict())

    @app.get("/director/status")
    async def director_status():
        sample = decide_persona_state({"conversation_state": "idle"})
        return JSONResponse(content={
            "ok": True,
            "name": "sophie_persona_director",
            "purpose": "fast deterministic state layer for Realtime, Claude, and avatar routing",
            "states": ["idle", "listening", "thinking", "speaking", "private_care", "work_focus", "high_risk", "waiting"],
            "sample": sample.to_dict(),
        })
