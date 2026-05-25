"""castle/server/livekit_endpoints.py - v0.10 Phase 2 - LiveKit WebRTC SFU integration

Endpoints:
  POST /livekit/token   - auth-gated - mint LiveKit access token (5 min expire)
  POST /livekit/spawn   - auth-gated - trigger Modal sophie-renderer worker join room
  GET  /livekit/health  - public     - check creds set (does not expose key)

Modal secret `livekit-creds` setup:
  python -m modal secret create livekit-creds \
    LIVEKIT_API_KEY=APIxxxxxxx \
    LIVEKIT_API_SECRET=secretxxxxxxxxxx \
    LIVEKIT_URL=wss://your-project.livekit.cloud

Notes:
  - Server SDK: livekit-api
  - Token TTL: 5 min (short expire by design)
  - Creds pulled from env (Modal secret), never hardcoded
  - Edward registers LiveKit Cloud personally (explicit_permission scope)
"""

from __future__ import annotations
import os
import time
import hashlib
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _resolve_livekit_creds():
    api_key = (os.environ.get("LIVEKIT_API_KEY") or os.environ.get("livekit_api_key") or "").strip()
    api_secret = (os.environ.get("LIVEKIT_API_SECRET") or os.environ.get("livekit_api_secret") or "").strip()
    url = (os.environ.get("LIVEKIT_URL") or os.environ.get("livekit_url") or "").strip()
    return api_key, api_secret, url


def _room_name_for(user_email):
    h = hashlib.sha256(user_email.encode("utf-8")).hexdigest()[:8]
    ts = int(time.time())
    return f"sophie-{h}-{ts}"


def attach_livekit_routes(app):
    """Mount LiveKit routes onto FastAPI app - auth-gated via middleware (cookie)."""

    @app.post("/livekit/token")
    async def _livekit_token(request: Request):
        api_key, api_secret, url = _resolve_livekit_creds()
        if not (api_key and api_secret and url):
            return JSONResponse(
                {
                    "ok": False,
                    "detail": "livekit creds missing - Modal secret `livekit-creds` not set or incomplete",
                    "missing": {
                        "LIVEKIT_API_KEY": not api_key,
                        "LIVEKIT_API_SECRET": not api_secret,
                        "LIVEKIT_URL": not url,
                    },
                },
                status_code=503,
            )

        try:
            from livekit import api as lkapi  # type: ignore
        except ImportError:
            return JSONResponse(
                {
                    "ok": False,
                    "detail": "livekit-api SDK not installed - add livekit-api to requirements.txt and redeploy",
                },
                status_code=503,
            )

        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}

        from castle.server.auth_middleware import COOKIE_NAME, verify_signed_cookie
        cookie_val = request.cookies.get(COOKIE_NAME, "")
        user_email = verify_signed_cookie(cookie_val) or "edward@unknown"

        room = body.get("room")
        if not room or not isinstance(room, str):
            room = _room_name_for(user_email)

        identity = f"edward-{int(time.time())}"
        ttl_s = 5 * 60

        try:
            grants = lkapi.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
            token = (
                lkapi.AccessToken(api_key, api_secret)
                .with_identity(identity)
                .with_name(user_email.split("@")[0])
                .with_grants(grants)
                .with_ttl(ttl_s)
                .to_jwt()
            )
        except Exception as e:
            logger.exception("[livekit] token mint fail")
            return JSONResponse(
                {"ok": False, "detail": f"token mint fail: {str(e)[:200]}"},
                status_code=500,
            )

        logger.info("[livekit] token minted - room=%s identity=%s ttl=%ds", room, identity, ttl_s)
        return JSONResponse(
            {
                "ok": True,
                "room": room,
                "token": token,
                "url": url,
                "identity": identity,
                "expires_in_s": ttl_s,
            }
        )

    @app.post("/livekit/spawn")
    async def _livekit_spawn(request: Request):
        """Trigger Modal sophie-renderer worker join room + start pushing frames.
        Body: {room: str (required), mode?: "idle"|"speaking" (default idle)}
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)

        room = body.get("room")
        if not room or not isinstance(room, str):
            return JSONResponse({"ok": False, "detail": "room missing"}, status_code=400)
        mode = body.get("mode", "idle")
        if mode not in ("idle", "speaking"):
            mode = "idle"

        try:
            import modal  # type: ignore
        except ImportError:
            return JSONResponse(
                {"ok": False, "detail": "modal SDK missing"}, status_code=503,
            )

        try:
            publisher_fn = modal.Function.from_name(
                "castle-voice-engine-musetalk-livekit-publisher",
                "publish_to_room",
            )
        except Exception as e:
            logger.warning("[livekit] modal publisher lookup fail: %s", str(e)[:200])
            return JSONResponse(
                {
                    "ok": False,
                    "detail": (
                        "modal publisher app not deployed - "
                        "deploy with: python -m modal deploy breeze_poc/app_musetalk_livekit_publisher.py"
                    ),
                },
                status_code=503,
            )

        try:
            call = publisher_fn.spawn(room=room, mode=mode)
            call_id = getattr(call, "object_id", None) or "unknown"
        except Exception as e:
            logger.exception("[livekit] modal spawn fail")
            return JSONResponse(
                {"ok": False, "detail": f"spawn fail: {str(e)[:200]}"},
                status_code=500,
            )

        logger.info("[livekit] spawned publisher - room=%s mode=%s call=%s", room, mode, call_id)
        return JSONResponse(
            {
                "ok": True,
                "status": "spawned",
                "room": room,
                "mode": mode,
                "modal_call_id": call_id,
            }
        )

    @app.get("/livekit/health")
    async def _livekit_health():
        """Public health check - does not expose secret."""
        api_key, api_secret, url = _resolve_livekit_creds()
        try:
            import livekit.api  # type: ignore  # noqa: F401
            sdk_ok = True
        except ImportError:
            sdk_ok = False
        try:
            import modal  # type: ignore  # noqa: F401
            modal_ok = True
        except ImportError:
            modal_ok = False
        return {
            "ok": bool(api_key and api_secret and url and sdk_ok and modal_ok),
            "livekit_creds_set": bool(api_key and api_secret and url),
            "livekit_url_set": bool(url),
            "livekit_sdk_installed": sdk_ok,
            "modal_sdk_installed": modal_ok,
            "phase": "v0.10 Phase 2",
        }
