# castle-voice-engine — Copyright (c) 2026 Edward / BeyondPath
# Built on PersonaPlex (NVIDIA, NOML) and Moshi (Kyutai, MIT)
# app.py — Modal deploy entrypoint. `modal deploy app.py` to push to A10G runtime.
#
# v0.1.1 — Added /test page for Chinese voice synthesis verification.
# Mounts the v0.1 WS engine at /voice via /ws routes (existing) and adds a
# minimal HTML test page + /test/synthesize POST that drives PersonaPlex
# offline inference to surface real Chinese voice capability.

from __future__ import annotations

import modal

# Build the Modal image:
#   - Debian slim + Python 3.11
#   - apt: git, ffmpeg, libopus-dev (Moshi audio codec dep)
#   - PIP: project requirements (FastAPI, uvicorn, websockets, PyYAML, torch, transformers)
#   - PIP: PersonaPlex (moshi-personaplex) installed from upstream NVIDIA repo
#   - Local castle/ source mounted at /root/castle
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libopus-dev", "libopus0")
    .pip_install_from_requirements("requirements.txt")
    .run_commands(
        # Clone PersonaPlex and install the moshi-personaplex package from the moshi/ subdir
        "git clone https://github.com/NVIDIA/personaplex.git /opt/personaplex",
        "pip install /opt/personaplex/moshi",
        "pip install accelerate soundfile",
    )
    .add_local_dir("castle", remote_path="/root/castle")
)

# Persistent volume for PersonaPlex weights (downloaded once, reused across cold starts).
weights_vol = modal.Volume.from_name("personaplex-weights", create_if_missing=True)

app = modal.App("castle-voice-engine")

# Single-tenant: max_containers=1 (PersonaPlex requires lock).
# Note: cve-auth secret no longer required for /test endpoints (auth bypass for v0.1.1 verify);
# huggingface secret is mandatory for PersonaPlex weight download.
@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 30,
    scaledown_window=120,  # cold start back to zero after 2 min idle
    volumes={"/cache/personaplex": weights_vol},
    secrets=[modal.Secret.from_name("huggingface")],
    max_containers=1,
)
@modal.asgi_app()
def fastapi_app():
    # Import inside the function so the local-side parse stays cheap.
    from castle.server.engine_server import app as fastapi_instance
    from castle.server.test_endpoints import attach_test_routes
    # Attach /test page + /test/synthesize POST onto the existing FastAPI app
    attach_test_routes(fastapi_instance)
    return fastapi_instance

# Local entrypoint for sanity check: `modal run app.py` will hit /health.
@app.local_entrypoint()
def smoke():
    import urllib.request
    import json
    url = fastapi_app.get_web_url() + "health"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
        print("health:", data)
