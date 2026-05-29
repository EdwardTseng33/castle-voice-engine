# castle-voice-engine / castle/server/vision_now_endpoints.py
# (c) 2026 Edward / BeyondPath
#
# v0.4.0 (2026-05-27): 真視覺接通 · Edward 5/27 拍板「動視覺」
#
# 設計:
#   - 前端瀏覽器抓 webcam frame · canvas.toBlob → JPEG 壓縮
#   - POST base64 image 到 /vision/analyze_now
#   - 後端送 Claude Haiku 4.5 vision · 拿描述
#   - 回傳描述 · 前端注入 OpenAI session 讓蘇菲講
#
# 跟舊架構差別:
#   - 舊 (cv2.VideoCapture on Modal): 雲端沒鏡頭 · 永遠 fail
#   - 新 (前端送 frame): 業界標準 (Zoom AI / Tavus / Google Meet AI 同方向)
#
# Budget guard:
#   - 月度上限 (環境變數 VISION_MONTHLY_BUDGET_USD · 預設 3.0 USD ≈ NT$90)
#   - 超過自動拒絕 · 回 budget_exceeded
#   - 每次呼叫 log 累計花費 (input tokens × $0.80/M + output tokens × $4/M)

from __future__ import annotations
import os
import time
import base64
import logging
from datetime import datetime
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("castle.vision_now")

# v0.4.0 預設月上限 USD$3 (~NT$90) · Edward 可調 VISION_MONTHLY_BUDGET_USD
DEFAULT_MONTHLY_BUDGET_USD = 3.0
HAIKU_INPUT_RATE_USD_PER_M = 0.80   # claude-haiku-4-5 input pricing
HAIKU_OUTPUT_RATE_USD_PER_M = 4.00  # claude-haiku-4-5 output pricing

# 蘇菲 persona-aware short observation prompt
SYSTEM_PROMPT = (
    "你是 Sophie · Edward 的貼身搭檔。你正透過 webcam 看 Edward。"
    "用台灣腔中文講一句 ≤ 25 字的觀察、不問問題、不下指令、不重複。"
    "範例: '你笑了喔'、'喝口水吧'、'你又在打字'、'坐久了肩膀僵'、'光變暗了'、'SKIP' (畫面無人/太暗)。"
)

# Module-level 月度花費追蹤 (process-local · Modal scale-down 後重置 · 簡易版)
_month_key = ""
_month_usd_spent = 0.0
_month_call_count = 0


def _current_month_key():
    return datetime.utcnow().strftime("%Y-%m")


def _reset_month_if_needed():
    global _month_key, _month_usd_spent, _month_call_count
    cur = _current_month_key()
    if cur != _month_key:
        _month_key = cur
        _month_usd_spent = 0.0
        _month_call_count = 0
        logger.info("[vision_now] month rolled · key=%s", cur)


def _record_spend(input_tokens: int, output_tokens: int):
    global _month_usd_spent, _month_call_count
    _reset_month_if_needed()
    cost = (input_tokens / 1_000_000) * HAIKU_INPUT_RATE_USD_PER_M + (output_tokens / 1_000_000) * HAIKU_OUTPUT_RATE_USD_PER_M
    _month_usd_spent += cost
    _month_call_count += 1
    return cost


def _budget_remaining_usd():
    _reset_month_if_needed()
    cap = float(os.environ.get("VISION_MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD))
    return cap - _month_usd_spent, cap


def attach_vision_now_routes(app):
    """Mount /vision/analyze_now + /vision/budget routes."""

    @app.post("/vision/analyze_now")
    async def analyze_now(request: Request):
        # 1. budget check
        remaining, cap = _budget_remaining_usd()
        if remaining <= 0:
            return JSONResponse({
                "ok": False,
                "error": "budget_exceeded",
                "detail": f"本月視覺花費已達上限 ${cap:.2f}",
                "month_usd_spent": round(_month_usd_spent, 4),
                "month_call_count": _month_call_count,
            }, status_code=429)

        # 2. parse body
        try:
            body = await request.json()
        except Exception as e:
            return JSONResponse({"ok": False, "error": "bad_body", "detail": str(e)[:200]}, status_code=400)
        b64 = body.get("image_base64", "")
        if not b64 or not isinstance(b64, str):
            return JSONResponse({"ok": False, "error": "no_image", "detail": "image_base64 missing"}, status_code=400)
        # 限長度 (防爆送)
        if len(b64) > 800_000:  # ~600KB image
            return JSONResponse({"ok": False, "error": "image_too_large", "detail": "max 600KB"}, status_code=413)

        # 3. anthropic SDK
        try:
            import anthropic  # type: ignore
        except ImportError:
            return JSONResponse({"ok": False, "error": "sdk_missing", "detail": "anthropic SDK not installed"}, status_code=503)

        # v0.4.1 fix (Edward 5/29「看不到我」)· Modal secret "anthropic-key" 的 env 變數名非標準
        #   brain_endpoints 能用 Claude 是因為它試 4 種名字、vision_now 之前只找 ANTHROPIC_API_KEY = 永遠 no_key
        #   → 同 brain 的多名解析
        anth_key = ""
        for _kname in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "anthropic_key", "ANTHROPIC", "anthropic-key"):
            _v = os.environ.get(_kname, "").strip()
            if _v:
                anth_key = _v
                break
        if not anth_key:
            return JSONResponse({"ok": False, "error": "no_key", "detail": "Anthropic key not found in env (tried 5 names)"}, status_code=503)

        # 4. call Claude vision
        t0 = time.time()
        try:
            client = anthropic.Anthropic(api_key=anth_key)
            resp = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=60,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                        },
                        {"type": "text", "text": "看一下"},
                    ],
                }],
            )
            latency_ms = round((time.time() - t0) * 1000, 1)
            obs_text = ""
            try:
                for block in resp.content:
                    if getattr(block, "type", "") == "text":
                        obs_text = getattr(block, "text", "").strip()
                        break
            except Exception:
                obs_text = str(resp.content)[:80]

            input_tok = getattr(resp.usage, "input_tokens", 0) if hasattr(resp, "usage") else 0
            output_tok = getattr(resp.usage, "output_tokens", 0) if hasattr(resp, "usage") else 0
            cost_usd = _record_spend(input_tok, output_tok)

            is_skip = obs_text.upper().startswith("SKIP") or obs_text == ""
            logger.info("[vision_now] obs='%s' latency=%dms cost=$%.5f tokens=%d/%d", obs_text[:40], latency_ms, cost_usd, input_tok, output_tok)

            return {
                "ok": True,
                "observation": obs_text,
                "is_skip": is_skip,
                "latency_ms": latency_ms,
                "tokens": {"input": input_tok, "output": output_tok},
                "cost_usd": round(cost_usd, 5),
                "month_usd_spent": round(_month_usd_spent, 4),
                "month_budget_usd": cap,
                "month_remaining_usd": round(remaining - cost_usd, 4),
            }
        except Exception as e:
            logger.exception("[vision_now] Claude call fail")
            return JSONResponse({
                "ok": False,
                "error": "claude_call_fail",
                "detail": str(e)[:300],
            }, status_code=502)

    @app.get("/vision/budget")
    async def vision_budget():
        remaining, cap = _budget_remaining_usd()
        return {
            "ok": True,
            "month_key": _month_key,
            "month_usd_spent": round(_month_usd_spent, 4),
            "month_budget_usd": cap,
            "month_remaining_usd": round(remaining, 4),
            "month_call_count": _month_call_count,
            "rate_input_per_M": HAIKU_INPUT_RATE_USD_PER_M,
            "rate_output_per_M": HAIKU_OUTPUT_RATE_USD_PER_M,
        }
