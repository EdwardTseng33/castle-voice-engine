# castle-voice-engine - v0.3.0 Phase 2 Path B (forked from v0.2.3 hotfix base)
# (c) 2026 Edward / BeyondPath
# castle/server/realtime_endpoints.py
#
# v0.3.0 (2026-05-22 Phase 2 Path B):
#   - Add /dispatch -> route OpenAI function-calls to castle subagents via Anthropic Claude
#     (turnip / calcifer / howl). Browser data-channel forwards function_call to here.
#   - Add /correct -> spaCy NER + homophone dict for Mandarin STT post-correction.
#   - Add /subagents -> list available subagents (browser UI use).
#   - Add /wake-status -> Picovoice readiness probe (currently placeholder).
#   - Add /health-extended -> full readiness probe (Edward verify Anthropic key etc).
#   - /sdp response now includes x-realtime-tools-b64 header so the browser can
#     attach function tools in its session.update event.
#
# v0.2.3 base (2026-05-22 hotfix #2): GA SDP endpoint /v1/realtime/calls.

from __future__ import annotations

import base64 as _b64
import json
import os
from pathlib import Path
from urllib.parse import quote as urlquote

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from castle.server.subagent_dispatcher import (
    dispatch_to_subagent,
    get_subagent_tools_spec,
    list_subagents,
)
from castle.server.text_correction import correct_text, get_dict_size
from castle.server import picovoice_stub

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


class DispatchRequest(BaseModel):
    subagent: str
    question: str
    context: str | None = None


class CorrectRequest(BaseModel):
    text: str
    use_spacy: bool = True


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
    tools_hint = (
        "\n\n--- Tools available (city subagents) ---\n"
        "你可以調用城堡 3 個 subagent 取得 domain 深度回答（透過 OpenAI function call）：\n"
        "- call_turnip：用戶研究 / persona / retention 數據\n"
        "- call_calcifer：技術 / 程式碼 / Bug / 估時\n"
        "- call_howl：產品策略 / 競品 / 商業判斷\n"
        "規則：自己能短答就短答（< 25 字）、需要 domain 深度才呼叫。subagent 回應拿到後用蘇菲的口吻講出來、不要 dump 原文。"
    )
    return prompt + suffix + tools_hint


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


async def _sanity_check_anthropic():
    key = (os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_KEY", "")).strip()
    if not key:
        return {"ok": False, "stage": "key_missing", "detail": "ANTHROPIC_API_KEY env var not set on Modal"}
    if not key.startswith("sk-ant-"):
        return {"ok": False, "stage": "key_malformed", "detail": "ANTHROPIC_API_KEY does not start with sk-ant-"}
    try:
        import anthropic
        import asyncio
        client = anthropic.Anthropic(api_key=key)
        loop = asyncio.get_running_loop()
        def _ping():
            return client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
        resp = await loop.run_in_executor(None, _ping)
        return {"ok": True, "stage": "ok", "model": "claude-sonnet-4-5", "stop_reason": getattr(resp, "stop_reason", None)}
    except Exception as e:
        return {"ok": False, "stage": "api_call", "detail": str(type(e).__name__) + ": " + str(e)}


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
        instr_b64 = _b64.b64encode(instructions.encode("utf-8")).decode("ascii")
        tools_spec = get_subagent_tools_spec()
        tools_b64 = _b64.b64encode(json.dumps(tools_spec, ensure_ascii=False).encode("utf-8")).decode("ascii")
        headers = {
            "x-realtime-model": used_model,
            "x-realtime-voice": voice,
            "x-realtime-persona": persona_name,
            "x-realtime-instructions-b64": instr_b64,
            "x-realtime-tools-b64": tools_b64,
            "x-realtime-tools-count": str(len(tools_spec)),
        }
        if warning:
            headers["x-realtime-warning"] = warning
            headers["x-realtime-fallback-from"] = req_model
        return PlainTextResponse(content=answer, media_type="application/sdp", headers=headers)


    # ---------- v0.3.0 Phase 2 new endpoints ----------

    @app.post("/dispatch")
    async def dispatch(req: DispatchRequest):
        result = await dispatch_to_subagent(req.subagent, req.question, req.context)
        return JSONResponse(content=result)

    @app.post("/correct")
    async def correct(req: CorrectRequest):
        try:
            result = correct_text(req.text, use_spacy=req.use_spacy)
            return JSONResponse(content=result)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "correction_failed", "detail": str(type(e).__name__) + ": " + str(e)})

    @app.get("/subagents")
    async def subagents_list():
        lst = list_subagents()
        return JSONResponse(content={"subagents": lst, "count": len(lst)})

    @app.get("/wake-status")
    async def wake_status():
        return JSONResponse(content=picovoice_stub.status())

    @app.get("/health-extended")
    async def health_extended():
        oa_key = os.environ.get("OPENAI_API_KEY", "").strip()
        an_check = await _sanity_check_anthropic()
        from castle.server.text_correction import _try_load_spacy
        spacy_ok = _try_load_spacy() is not None
        lst = list_subagents()
        return JSONResponse(content={
            "openai_key": {"present": bool(oa_key), "prefix_ok": oa_key.startswith(("sk-", "sess-")) if oa_key else False},
            "anthropic": an_check,
            "spacy_zh": {"available": spacy_ok},
            "correction_dict_size": get_dict_size(),
            "subagents_loaded": len(lst),
            "subagents": [s["name"] for s in lst],
            "picovoice": picovoice_stub.status(),
        })
