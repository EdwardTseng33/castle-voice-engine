# castle-voice-engine / castle/server/eval_endpoints.py
# (c) 2026 Edward / BeyondPath
# TEST-ONLY endpoints - 2026-06-02 calcifer - model objective eval.
# Fair compare 3 deep-brain candidates (Claude Opus / Claude Sonnet / GPT 5.5).
# staging lacks a GPT deep line + shared vision test path, so add here.
# prod behaviour unchanged:
#   POST /brain/ask_gpt          GPT chat line (mirrors ask_claude)
#   POST /brain/eval_vision      vision path all 3 take (does NOT touch /vision/analyze_now $3 guard)
#   GET  /brain/list_gpt_models  list OpenAI model ids (confirm real GPT 5.5 id)
from __future__ import annotations
import os
import time
import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _resolve_openai_key():
    for name in ("OPENAI_API_KEY", "OPENAI_KEY", "openai_key", "OPENAI"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return None


def _resolve_anthropic_key():
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "anthropic_key", "ANTHROPIC", "anthropic-key"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return None


SOPHIE_BRAIN_SYSTEM = (
    "You are Sophie, the deep-thinking brain of Edward's personal AI assistant. "
    "Edward asks you a question that needs real thought via Voice Path. "
    "Speak as Sophie: firm, plain, no flattery, first person. "
    "Reply in zh-TW, concise, under 120 chars, no bullet points, give the answer directly. "
    "If you need more context to answer, say so directly."
)

GPT_MODEL_FALLBACKS = ["gpt-5.5", "gpt-5.5-chat", "gpt-5.5-turbo", "gpt-5", "gpt-4.1", "gpt-4o"]


def attach_eval_routes(app):

    @app.get("/brain/list_gpt_models")
    async def _list_gpt_models():
        key = _resolve_openai_key()
        if not key:
            return JSONResponse({"ok": False, "detail": "openai key missing"}, status_code=200)
        try:
            from openai import OpenAI
        except ImportError:
            return JSONResponse({"ok": False, "detail": "openai sdk missing"}, status_code=200)
        try:
            client = OpenAI(api_key=key)
            models = client.models.list()
            ids = sorted([m.id for m in models.data])
            gpt5 = [i for i in ids if "gpt-5" in i]
            return JSONResponse({"ok": True, "count": len(ids), "gpt5_candidates": gpt5, "all": ids})
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:300]}, status_code=200)

    @app.post("/brain/ask_gpt")
    async def _ask_gpt(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        question = body.get("question")
        context = body.get("context", "")
        if not question or not isinstance(question, str):
            return JSONResponse({"ok": False, "detail": "question missing"}, status_code=400)
        _test_model = body.get("_model")
        _test_maxtok = body.get("_max_tokens")
        use_maxtok = _test_maxtok if isinstance(_test_maxtok, int) and 50 <= _test_maxtok <= 2000 else 200
        key = _resolve_openai_key()
        if not key:
            return JSONResponse({"ok": False, "detail": "openai key missing", "answer": ""}, status_code=200)
        from openai import OpenAI
        client = OpenAI(api_key=key)
        candidates = ([_test_model] if isinstance(_test_model, str) and _test_model else []) + GPT_MODEL_FALLBACKS
        user_content = (("[ctx]\n" + context + "\n\n") if context else "") + "[Edward]\n" + question
        last_err = None
        for model in candidates:
            t0 = time.time()
            try:
                try:
                    resp = client.chat.completions.create(model=model, max_completion_tokens=use_maxtok, messages=[{"role": "system", "content": SOPHIE_BRAIN_SYSTEM}, {"role": "user", "content": user_content}])
                except Exception as e_param:
                    se = str(e_param)
                    if ("max_completion_tokens" in se) or ("max_tokens" in se) or ("temperature" in se) or ("Unsupported" in se):
                        resp = client.chat.completions.create(model=model, max_tokens=use_maxtok, messages=[{"role": "system", "content": SOPHIE_BRAIN_SYSTEM}, {"role": "user", "content": user_content}])
                    else:
                        raise
                dt_ms = int((time.time() - t0) * 1000)
                answer = (resp.choices[0].message.content or "").strip()
                return JSONResponse({"ok": True, "answer": answer, "gen_ms": dt_ms, "model": model, "model_requested": _test_model or "auto", "max_tokens": use_maxtok})
            except Exception as e:
                last_err = model + ": " + str(e)[:150]
                continue
        return JSONResponse({"ok": False, "detail": "all GPT models failed", "last_err": str(last_err), "answer": "", "tried": candidates}, status_code=200)

    @app.post("/brain/eval_vision")
    async def _eval_vision(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        b64 = body.get("image_base64", "")
        if not b64 or not isinstance(b64, str):
            return JSONResponse({"ok": False, "detail": "image_base64 missing"}, status_code=400)
        question = body.get("question") or "Describe this persons emotion and what they are doing, in one sentence."
        provider = (body.get("provider") or "").strip().lower()
        model = body.get("_model")
        use_maxtok = body.get("_max_tokens")
        use_maxtok = use_maxtok if isinstance(use_maxtok, int) and 50 <= use_maxtok <= 500 else 150
        if not provider:
            provider = "claude" if (isinstance(model, str) and "claude" in model) else "gpt"
        if provider == "claude":
            key = _resolve_anthropic_key()
            if not key:
                return JSONResponse({"ok": False, "detail": "anthropic key missing"}, status_code=200)
            import anthropic
            use_model = model if isinstance(model, str) and model else "claude-sonnet-4-6"
            t0 = time.time()
            try:
                client = anthropic.Anthropic(api_key=key)
                resp = client.messages.create(model=use_model, max_tokens=use_maxtok, messages=[{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}, {"type": "text", "text": question}]}])
                dt_ms = int((time.time() - t0) * 1000)
                answer = resp.content[0].text if resp.content else ""
                return JSONResponse({"ok": True, "provider": "claude", "model": use_model, "gen_ms": dt_ms, "answer": answer.strip()})
            except Exception as e:
                return JSONResponse({"ok": False, "provider": "claude", "model": use_model, "detail": str(e)[:300]}, status_code=200)
        else:
            key = _resolve_openai_key()
            if not key:
                return JSONResponse({"ok": False, "detail": "openai key missing"}, status_code=200)
            from openai import OpenAI
            client = OpenAI(api_key=key)
            candidates = ([model] if isinstance(model, str) and model else []) + GPT_MODEL_FALLBACKS
            data_url = "data:image/jpeg;base64," + b64
            last_err = None
            for m in candidates:
                t0 = time.time()
                try:
                    try:
                        resp = client.chat.completions.create(model=m, max_completion_tokens=use_maxtok, messages=[{"role": "user", "content": [{"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": data_url}}]}])
                    except Exception as e_param:
                        se = str(e_param)
                        if ("max_completion_tokens" in se) or ("max_tokens" in se) or ("temperature" in se) or ("Unsupported" in se):
                            resp = client.chat.completions.create(model=m, max_tokens=use_maxtok, messages=[{"role": "user", "content": [{"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": data_url}}]}])
                        else:
                            raise
                    dt_ms = int((time.time() - t0) * 1000)
                    answer = (resp.choices[0].message.content or "").strip()
                    return JSONResponse({"ok": True, "provider": "gpt", "model": m, "model_requested": model or "auto", "gen_ms": dt_ms, "answer": answer})
                except Exception as e:
                    last_err = m + ": " + str(e)[:150]
                    continue
            return JSONResponse({"ok": False, "provider": "gpt", "detail": "all GPT vision failed", "last_err": str(last_err), "tried": candidates}, status_code=200)
