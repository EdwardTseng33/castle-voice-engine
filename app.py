# castle-voice-engine - Copyright (c) 2026 Edward / BeyondPath
# app.py - Modal deploy entrypoint. `modal deploy app.py` to push runtime.
#
# v0.3.0 (2026-05-22): Phase 3 multimodal - camera + MediaPipe + Claude vision.
#   - New /camera/* endpoints (enable / disable / kill / status / snapshot)
#   - New /vision/* endpoints (enable / disable / status / latest)
#   - Privacy default OFF, user must POST /camera/enable explicitly
#   - Kill switch <= 200ms (Incident 7.3)
#   - Requires Modal secret "anthropic" for Claude vision API
#
# v0.2.3 (2026-05-22 hotfix #2): switch OpenAI SDP target to /v1/realtime/calls (GA)
# v0.2.0 (2026-05-22): gpt-realtime-2 upgrade + browser demo at /
# v0.1.5 (2026-04-27): PersonaPlex -> OpenAI Realtime.
#
# What this Modal app does now:
#   - Slim Python 3.11 image with mediapipe + opencv + anthropic + Pillow added.
#   - Mounts castle/ source (incl. castle/static/index.html demo).
#   - Reads master OPENAI_API_KEY from Modal secret "openai".
#   - Reads ANTHROPIC_API_KEY from Modal secret "anthropic" (Phase 3).
#   - Exposes:
#       GET  /                    -> redirect to /static/index.html (browser demo)
#       GET  /health              -> status
#       GET  /personas            -> list registered personas
#       POST /session/token       -> (410 Gone)
#       POST /sdp                 -> WebRTC SDP exchange for browser
#       POST /camera/enable       -> open webcam (Privacy 5.1 opt-in)
#       POST /camera/disable      -> graceful stop
#       POST /camera/kill         -> emergency stop <= 200ms
#       GET  /camera/status       -> camera + vision state
#       GET  /camera/snapshot     -> debug only (env CAMERA_DEBUG=1)
#       POST /vision/enable       -> start Claude vision narration loop
#       POST /vision/disable      -> stop loop
#       GET  /vision/status       -> narration stats
#       GET  /vision/latest       -> latest observation for browser polling
#       GET  /static/*            -> static demo assets

from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir("castle", remote_path="/root/castle")
)

app = modal.App("castle-voice-engine")


@app.function(
    image=image,
    timeout=120,
    scaledown_window=120,
    secrets=[
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("anthropic-key"),
        modal.Secret.from_name("tavus"),  # v0.3.2 Phase 3.2 Tavus CVI 即時對話
    ],
)
@modal.asgi_app()
def fastapi_app():
    from pathlib import Path

    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles

    from castle.server.engine_server import app as fastapi_instance
    from castle.server.realtime_endpoints import attach_realtime_routes
    from castle.server.camera_endpoints import attach_camera_routes
    from castle.server.dispatch_endpoints import attach_dispatch_routes
    from castle.server.tavus_endpoints import attach_tavus_routes

    attach_realtime_routes(fastapi_instance)
    attach_camera_routes(fastapi_instance)
    attach_dispatch_routes(fastapi_instance)  # v0.3.0 Phase 2 後半段: castle dispatch + phase2/status
    attach_tavus_routes(fastapi_instance)  # v0.3.2 Phase 3.2: Tavus CVI 即時對話 video

    # v0.9.6 Google OAuth 認證 (Edward 5/23 拍板)
    from fastapi import Request
    from fastapi.responses import JSONResponse, Response
    from pydantic import BaseModel
    from castle.server.auth_middleware import (
        verify_google_id_token,
        sign_email_cookie,
        verify_signed_cookie,
        is_public_path,
        COOKIE_NAME,
        COOKIE_MAX_AGE,
    )

    class AuthVerifyReq(BaseModel):
        credential: str

    @fastapi_instance.post("/auth/verify")
    async def _auth_verify(req: AuthVerifyReq):
        email = verify_google_id_token(req.credential)
        if not email:
            return JSONResponse(
                {"ok": False, "detail": "此 Google 帳號未授權 · 只允許 Edward 本人"},
                status_code=403,
            )
        signed = sign_email_cookie(email)
        resp = JSONResponse({"ok": True, "email": email})
        resp.set_cookie(
            key=COOKIE_NAME,
            value=signed,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        return resp

    @fastapi_instance.get("/auth/whoami")
    async def _auth_whoami(request: Request):
        cookie = request.cookies.get(COOKIE_NAME)
        email = verify_signed_cookie(cookie) if cookie else None
        if email:
            return {"ok": True, "email": email}
        return JSONResponse({"ok": False}, status_code=401)

    @fastapi_instance.post("/auth/logout")
    async def _auth_logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

    # Mount /static for demo HTML + add root redirect.
    # v0.4.2 fix: 強制不快取 (避免 Edward 瀏覽器 cache 舊版本 / 每次 push 都要 Ctrl+Shift+R)
    static_dir = Path("/root/castle/static")
    if static_dir.exists():
        fastapi_instance.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

        @fastapi_instance.get("/")
        async def _root(request: Request):
            cookie = request.cookies.get(COOKIE_NAME)
            email = verify_signed_cookie(cookie) if cookie else None
            if email:
                return RedirectResponse(url="/static/index.html")
            return RedirectResponse(url="/static/auth.html")

        # v0.4.2 · 替 /static/* 加 no-cache header (確保 Edward 永遠拿最新版)
        # v0.9.6 · 加 Google OAuth gate (除 /static/auth.html 外 · 都需 cookie 認)
        @fastapi_instance.middleware("http")
        async def _cache_and_auth_middleware(request, call_next):
            path = request.url.path

            # auth gate · skip public paths
            if not is_public_path(path):
                # /static/* (except auth.html 已在 PUBLIC_EXACT) · /camera/* · /vision/* · /dispatch/* · /tavus/* · /sdp · /personas etc
                # /sdp 也守 · WebRTC handshake 必須認 · 防別人燒 OpenAI cost
                cookie = request.cookies.get(COOKIE_NAME)
                email = verify_signed_cookie(cookie) if cookie else None
                if not email:
                    # auth.html 自己 / 圖片 / mp4 / js / css 全擋 · 沒 cookie 啥都看不到
                    if path.startswith("/static/"):
                        # 把 user redirect 到 auth.html
                        return RedirectResponse(url="/static/auth.html")
                    # API endpoints (sdp / camera / vision / dispatch / tavus / session)
                    return JSONResponse({"ok": False, "detail": "請先登入"}, status_code=401)

            resp = await call_next(request)
            if path.startswith("/static/"):
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
            return resp

    return fastapi_instance


@app.local_entrypoint()
def smoke():
    import urllib.request
    import json
    url = fastapi_app.get_web_url() + "health"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
        print("health:", data)
