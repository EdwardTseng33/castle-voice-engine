# castle-voice-engine — Copyright (c) 2026 Edward / BeyondPath
# Built on PersonaPlex (NVIDIA, NOML) and Moshi (Kyutai, MIT)
# app.py — Modal deploy entrypoint. `modal deploy app.py` to push to A10G runtime.

from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install_from_requirements("requirements.txt")
    # PersonaPlex weights are NOT bundled here — pull at runtime via volume mount.
    .add_local_dir("castle", remote_path="/root/castle")
)

# Persistent volume for PersonaPlex weights (downloaded once, reused across cold starts).
weights_vol = modal.Volume.from_name("personaplex-weights", create_if_missing=True)

app = modal.App("castle-voice-engine")

# Single-tenant: keep_warm=0 (scale-to-zero), max_containers=1 (PersonaPlex requires lock).
@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 30,
    container_idle_timeout=60,  # cold start back to zero after 1 min idle
    volumes={"/cache/personaplex": weights_vol},
    secrets=[modal.Secret.from_name("cve-auth", required_keys=["CVE_AUTH_TOKEN"])],
    max_containers=1,
)
@modal.asgi_app()
def fastapi_app():
    # Import inside the function so the local-side parse stays cheap.
    from castle.server.engine_server import app as fastapi_instance
    return fastapi_instance

# Local entrypoint for sanity check: `modal run app.py` will hit /health.
@app.local_entrypoint()
def smoke():
    import urllib.request
    import json
    url = fastapi_app.web_url + "health"  # type: ignore[attr-defined]
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
        print("health:", data)
