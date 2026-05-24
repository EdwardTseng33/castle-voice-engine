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
from fastapi import Request  # module-level import · 防 from __future__ import annotations 讓 FastAPI 在 closure 內 resolve Request type 失敗 → 422 query.X missing

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir("castle", remote_path="/root/castle")
)

app = modal.App("castle-voice-engine")

# v1.5.0 · 嘴對齊 100 句預生 mp4 cache · 共用 modal.Volume sophie-lipsync-cache
lipsync_volume = modal.Volume.from_name("sophie-lipsync-cache", create_if_missing=True)


@app.function(
    image=image,
    timeout=120,
    scaledown_window=120,
    secrets=[
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("anthropic-key"),
        modal.Secret.from_name("tavus"),  # v0.3.2 Phase 3.2 Tavus CVI 即時對話
        modal.Secret.from_name("castle-dev-bypass"),  # v2.x · dev bypass header + DEV_BYPASS_ENABLED env (cron Path B + dev_endpoints 3 gate)
    ],
    volumes={"/lipsync_cache": lipsync_volume},  # v1.5.0 · 100 句嘴對齊 mp4
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
    from castle.server.memory_endpoints import attach_memory_routes  # v1.1.2 IndexedDB summary backend
    from castle.server.brain_endpoints import attach_brain_routes  # v1.6.0 Claude 真大腦 + 派工接口
    from castle.server.dev_endpoints import attach_dev_routes  # v1.5.1 馬魯克 · 自動驗收 dev endpoint

    attach_realtime_routes(fastapi_instance)
    attach_camera_routes(fastapi_instance)
    attach_dispatch_routes(fastapi_instance)  # v0.3.0 Phase 2 後半段: castle dispatch + phase2/status
    attach_tavus_routes(fastapi_instance)  # v0.3.2 Phase 3.2: Tavus CVI 即時對話 video
    attach_memory_routes(fastapi_instance)  # v1.1.2 Phase 3.3: 記憶連續性 (Claude Haiku 摘要 · 後端 stateless)
    attach_brain_routes(fastapi_instance)  # v1.6.0 雙腦混合 · ask_claude / dispatch_howl / dispatch_code
    attach_dev_routes(fastapi_instance)    # v1.5.1 馬魯克 · /dev/simulate_realtime + /dev/health (dev only)

    # v1.5.0 · 嘴對齊 100 句預生 mp4 serve · 從 modal.Volume sophie-lipsync-cache 讀
    import os as _os
    import json as _json
    from fastapi.responses import FileResponse
    LIPSYNC_DIR = "/lipsync_cache"

    @fastapi_instance.get("/lipsync/manifest.json")
    async def _lipsync_manifest():
        try:
            lipsync_volume.reload()
        except Exception:
            pass
        mf = f"{LIPSYNC_DIR}/manifest.json"
        if not _os.path.exists(mf):
            return JSONResponse({"phrases": [], "total": 0})
        try:
            with open(mf, "r", encoding="utf-8") as f:
                return JSONResponse(_json.load(f))
        except Exception as e:
            return JSONResponse({"phrases": [], "total": 0, "error": str(e)[:200]})

    @fastapi_instance.get("/lipsync/{phrase_file}")
    async def _lipsync_file(phrase_file: str):
        # 防 path traversal · 只接受 phrase_XXX.mp4
        if not phrase_file.startswith("phrase_") or not phrase_file.endswith(".mp4"):
            return JSONResponse({"detail": "bad phrase_file"}, status_code=400)
        try:
            lipsync_volume.reload()
        except Exception:
            pass
        full = f"{LIPSYNC_DIR}/{phrase_file}"
        if not _os.path.exists(full):
            return JSONResponse({"detail": "not found"}, status_code=404)
        return FileResponse(full, media_type="video/mp4")

    # v0.9.6 Google OAuth 認證 (Edward 5/23 拍板)
    # Request 已在 module-level import (line 40) · 不在 closure 內 re-import (避免 from __future__ annotations 解析 fail)
    from fastapi.responses import JSONResponse, Response
    from pydantic import BaseModel
    from castle.server.auth_middleware import (
        verify_google_id_token,
        sign_email_cookie,
        verify_signed_cookie,
        is_public_path,
        COOKIE_NAME,
        COOKIE_MAX_AGE,
        ALLOWED_EMAILS,
        DEV_CRON_EMAIL,
    )
    # v1.5.1 Suliman Tier B Seg 2 fix · dev bypass cookie set 副作用支援
    from castle.server.dev_endpoints import (
        is_valid_dev_bypass,
        DEV_BYPASS_HEADER,
    )

    from castle.server.auth_middleware import verify_google_id_token_any, OWNER_CONTACT_EMAIL

    @fastapi_instance.post("/auth/verify")
    async def _auth_verify(request: Request):
        # v1.2.0a fix · 直接拿 raw Request body · 避開 BaseModel in closure 被 from __future__ annotations 卡 422
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body 解析失敗"}, status_code=400)
        credential = body.get("credential") if isinstance(body, dict) else None
        if not credential or not isinstance(credential, str):
            return JSONResponse({"ok": False, "detail": "credential 缺失"}, status_code=400)
        # v1.2.0 訪客模式 · 解析 token 但只在 allow list 才簽 cookie · 不在 allow list 也告知對方 email
        email, allowed = verify_google_id_token_any(credential)
        if not email:
            # token 假 / 簽名錯 / email_verified=False → 真假冒、不告訴 contact 細節
            return JSONResponse(
                {"ok": False, "detail": "Google 驗證失敗 · 請重試"},
                status_code=400,
            )
        if not allowed:
            # 真實 Google 帳號但不在 allow list · 顯示邀請畫面用的 contact + 對方剛登入的 email
            return JSONResponse(
                {
                    "ok": False,
                    "detail": "這是 Edward 的個人 AI 蘇菲 · 需 Edward 親自授權才能使用",
                    "contact": OWNER_CONTACT_EMAIL,
                    "your_email": email,
                },
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
        """v1.5.1 Suliman Tier B Seg 2 fix · dev bypass cookie set 副作用

        Path A (一般 user)：有 cookie + verify_signed_cookie OK → 回 email
        Path B (dev cron)：無 cookie 但帶 X-Castle-Dev-Bypass header + DEV_BYPASS_ENABLED=1 →
                          mint short-lived (30 min) DEV_CRON_EMAIL cookie · 後續 navigation 免帶 header
        Path C (其他)：401

        prod 環境未設 DEV_BYPASS_ENABLED → Path B 永遠失敗 (is_valid_dev_bypass 回 False)
        """
        # Path A · 已有 cookie · 走原 verify
        cookie = request.cookies.get(COOKIE_NAME)
        email = verify_signed_cookie(cookie) if cookie else None
        if email:
            return {"ok": True, "email": email}

        # Path B · dev bypass header → mint 30 min DEV_CRON_EMAIL cookie
        # 觸發條件 (任一缺即失敗)：
        #   1. DEV_BYPASS_ENABLED env == "1" (在 dev_endpoints._DEV_EXPLICITLY_ENABLED 判)
        #   2. CASTLE_DEV_BYPASS_TOKEN env 非空 (上同)
        #   3. request 帶 X-Castle-Dev-Bypass header · token 對
        if is_valid_dev_bypass(request):
            dev_signed = sign_email_cookie(DEV_CRON_EMAIL)
            resp = JSONResponse({"ok": True, "email": DEV_CRON_EMAIL, "mode": "dev-cron"})
            resp.set_cookie(
                key=COOKIE_NAME,
                value=dev_signed,
                max_age=1800,  # 30 min · 短時效縮小 blast radius
                httponly=True,
                secure=True,
                samesite="lax",
                path="/",
            )
            return resp

        # Path C · 401
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
        async def _root():
            # v1.2.0a fix · 砍 request: Request 參數 (Modal serverless closure 內 type hint resolve fail · 422 query.request missing)
            # 純 redirect 不需要 request object · 直接無參數定義最穩
            return RedirectResponse(url="/static/index.html")

        # v0.4.2 · 替 /static/* 加 no-cache header (確保 Edward 永遠拿最新版)
        # v0.9.6 · 加 Google OAuth gate (除 /static/auth.html 外 · 都需 cookie 認)
        # v1.2.0 · 訪客模式 · /static/* 全公開 (UI shell / mp4 / sw.js / js / css) · 只 API endpoints 守認證
        #          燒錢 / 涉互動 / 涉隱私 API：/sdp · /camera/* · /vision/* · /dispatch/* · /tavus/* · /memory/* · /session/* · /personas
        #          (PUBLIC_PREFIX 已加 /static/ · is_public_path 直接放行 static/* + auth flow + health)
        @fastapi_instance.middleware("http")
        async def _cache_and_auth_middleware(request, call_next):
            path = request.url.path

            # auth gate · skip public paths (含整個 /static/* · v1.2.0 訪客模式)
            if not is_public_path(path):
                # API endpoints (/sdp · /camera/* · /vision/* · /dispatch/* · /tavus/* · /memory/* · /session/* · /personas etc)
                # /sdp 守 · WebRTC handshake 必須認 · 防別人燒 OpenAI cost
                # /memory/* 守 · 防別人燒 Anthropic cost + 隱私
                cookie = request.cookies.get(COOKIE_NAME)
                email = verify_signed_cookie(cookie) if cookie else None
                if not email:
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
