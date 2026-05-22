# castle-voice-engine - Copyright (c) 2026 Edward / BeyondPath
# app.py - Modal deploy entrypoint. `modal deploy app.py` to push runtime.
#
# v0.2.0 (2026-05-22): gpt-realtime-2 upgrade + browser demo at /
#   - realtime_endpoints.py now defaults to gpt-realtime-2 (5/8 release) with
#     auto-fallback to gpt-realtime on model_not_found.
#   - New POST /sdp endpoint: browser WebRTC SDP exchange (preferred over WS).
#   - Demo HTML mounted at /static and / redirects there. Edward opens / in a
#     browser, clicks the button, speaks Mandarin, Sophie speaks back.
#
# v0.1.5 (2026-04-27): PersonaPlex -> OpenAI Realtime.
#
# What this Modal app does now:
#   - Slim Python 3.11 image (no GPU, no torch, no transformers).
#   - Mounts castle/ source (incl. castle/static/index.html demo).
#   - Reads master OPENAI_API_KEY from Modal secret "openai".
#   - Exposes:
#       GET  /                    -> redirect to /static/index.html (browser demo)
#       GET  /health              -> status
#       GET  /personas            -> list registered personas
#       POST /session/token       -> mint ephemeral OpenAI Realtime client_secret
#       POST /sdp                 -> WebRTC SDP exchange for browser
#       GET  /static/*            -> static demo assets
#       (legacy) GET/POST /voice  -> PersonaPlex stub WebSocket (kept, not used)

from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir("castle", remote_path="/root/castle")
)

app = modal.App("castle-voice-engine")


@app.function(
    image=image,
    timeout=60,
    scaledown_window=120,
    secrets=[modal.Secret.from_name("openai")],
)
@modal.asgi_app()
def fastapi_app():
    from pathlib import Path

    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles

    from castle.server.engine_server import app as fastapi_instance
    from castle.server.realtime_endpoints import attach_realtime_routes

    attach_realtime_routes(fastapi_instance)

    # v0.2.0: mount /static for demo HTML + add root redirect.
    static_dir = Path("/root/castle/static")
    if static_dir.exists():
        fastapi_instance.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

        @fastapi_instance.get("/")
        async def _root():
            return RedirectResponse(url="/static/index.html")

    return fastapi_instance


@app.local_entrypoint()
def smoke():
    import urllib.request
    import json
    url = fastapi_app.get_web_url() + "health"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
        print("health:", data)
