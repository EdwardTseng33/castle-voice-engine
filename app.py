# castle-voice-engine - Copyright (c) 2026 Edward / BeyondPath
# app.py - Modal deploy entrypoint. `modal deploy app.py` to push runtime.
#
# v0.1.5 - Voice backend swap: PersonaPlex (NVIDIA NOML) -> OpenAI Realtime API.
#
# Reason for swap:
#   - v0.1.1 PersonaPlex audition (commit 369ae55, /test page) confirmed the
#     7B base model is OOD on system-prompt steering: regardless of zh-TW
#     input, output collapsed to "say hello". Calcifer's pre-deploy risk
#     prediction held.
#   - Edward + Sophie audited voice vendors (2026-04-27): OpenAI Realtime
#     wins on (a) production-grade Mandarin, (b) unified speech-to-speech
#     (no STT/TTS glue), (c) cost ~$0.06/min in + $0.24/min out fits dev.
#   - v0.1.1 /test page + /test/synthesize POST kept on disk
#     (castle/server/test_endpoints.py) as deprecated archive but no longer
#     attached to the running app. Image build no longer downloads the 14GB
#     PersonaPlex weights -> cold start drops from ~5-8 min to seconds.
#
# What this Modal app does now:
#   - Slim Python 3.11 image (no GPU, no torch, no transformers).
#   - Mounts castle/ source.
#   - Reads master OPENAI_API_KEY from Modal secret "openai".
#   - Exposes:
#       GET  /health              -> status
#       GET  /personas            -> list registered personas
#       POST /session/token       -> mint ephemeral OpenAI Realtime client_secret
#       (legacy) GET/POST /voice  -> PersonaPlex stub WebSocket (kept, not used)
#
# Future (v0.3+ voice cloning):
#   - The huggingface secret is no longer required at runtime, but will be
#     reattached when we evaluate self-hosted voice cloning options.

from __future__ import annotations

import modal

# Slim image - no GPU, no PersonaPlex/Moshi runtime, no 14GB model download.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir("castle", remote_path="/root/castle")
)

app = modal.App("castle-voice-engine")

# CPU-only function. No GPU needed for ephemeral-token mint -- the heavy
# audio inference happens inside OpenAI's infra after the browser connects
# directly to wss://api.openai.com/v1/realtime.
#
# `max_containers` removed: ephemeral token mint is stateless, scale freely.
@app.function(
    image=image,
    timeout=60,
    scaledown_window=120,  # idle scale-to-zero after 2 min
    secrets=[modal.Secret.from_name("openai")],
)
@modal.asgi_app()
def fastapi_app():
    # Import inside the function so local-side parse stays cheap.
    from castle.server.engine_server import app as fastapi_instance
    from castle.server.realtime_endpoints import attach_realtime_routes

    # Attach OpenAI Realtime ephemeral-token endpoint. v0.1.1 PersonaPlex
    # /test routes deliberately NOT attached -- file kept on disk as archive.
    attach_realtime_routes(fastapi_instance)
    return fastapi_instance


# Local sanity check: `modal run app.py` will hit /health.
@app.local_entrypoint()
def smoke():
    import urllib.request
    import json
    url = fastapi_app.get_web_url() + "health"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
        print("health:", data)
