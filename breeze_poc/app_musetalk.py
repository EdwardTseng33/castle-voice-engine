# breeze_poc/app_musetalk.py
# Voice Path v0.7 · MuseTalk v1.5 lipsync · Modal app
# (c) 2026 Edward / BeyondPath
# MuseTalk v1.5 by Lyra Lab, Tencent Music Entertainment (MIT License)
# https://github.com/TMElyralab/MuseTalk
#
# Dependencies attribution:
#   - OpenAI Whisper (MIT)
#   - IDEA-Research DWPose (Apache-2.0)
#   - ft-mse-vae (CreativeML Open RAIL-M · Track B audit required for commercial use)
#   - S3FD (license verification pending)
#
# Tested matrix (from MuseTalk official README + requirements.txt + inference.sh):
#   - Python 3.10
#   - CUDA 11.7 client + Modal host driver 580 (NVIDIA forward compat OK)
#   - torch 2.0.1+cu117
#   - GPU: A10G ($1.10/hr · scale-to-zero · scaledown_window=60)
#   - No flash-attn / no source-build wheels
#
# Architecture (Edward 2026-05-23 拍板):
#   聽 = Breeze ASR-25 (castle-voice-engine-breeze-poc)
#   說 = OpenAI gpt-realtime-2 (castle/server/realtime_endpoints.py · marin voice + Sophie persona)
#   嘴 = MuseTalk (this app)
#
# Endpoints:
#   GET  /musetalk/health        - warm + model status
#   POST /musetalk/enroll        - upload reference face (subject_guard required)
#   WS   /musetalk/stream        - audio chunks in, H264 video frames out

import modal

# ---------------------------------------------------------------------------
# Modal image · independent from breeze (different python + torch pin)
# ---------------------------------------------------------------------------

musetalk_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "libgl1", "libglib2.0-0", "wget")
    .pip_install(
        "torch==2.0.1",
        "torchvision==0.15.2",
        "torchaudio==2.0.2",
        extra_index_url="https://download.pytorch.org/whl/cu117",
    )
    .pip_install(
        # MuseTalk official requirements.txt (pinned)
        "diffusers==0.30.2",
        "accelerate==0.28.0",
        "numpy==1.23.5",
        "tensorflow==2.12.0",
        "tensorboard==2.12.0",
        "opencv-python==4.9.0.80",
        "soundfile==0.12.1",
        "transformers==4.39.2",
        "huggingface_hub==0.30.2",
        "einops==0.8.1",
        "gdown",
        "requests",
        "imageio[ffmpeg]",
        "omegaconf",
        "ffmpeg-python",
        "moviepy",
        # FastAPI server (kept inside main image so the asgi_app share cache)
        "fastapi>=0.110,<0.116",
        "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0",
        "python-multipart>=0.0.9",
    )
    .run_commands(
        "cd /root && git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git",
    )
)

app = modal.App("castle-voice-engine-musetalk-poc")

MUSETALK_AUTH_TOKEN_SECRET = modal.Secret.from_name("musetalk-poc-auth")
HF_SECRET = modal.Secret.from_name("huggingface", required_keys=[])

# Persisted volume so model weights (~10-15 GB) only download once
MUSETALK_VOLUME = modal.Volume.from_name("musetalk-weights", create_if_missing=True)


# ---------------------------------------------------------------------------
# Inference class
# ---------------------------------------------------------------------------


@app.cls(
    image=musetalk_image,
    gpu="A10G",
    memory=24576,
    timeout=900,
    scaledown_window=60,
    secrets=[MUSETALK_AUTH_TOKEN_SECRET, HF_SECRET],
    volumes={"/weights": MUSETALK_VOLUME},
    min_containers=0,
)
class MuseTalkRunner:
    """MuseTalk lipsync inference · cold-start ~5-8s once weights cached."""

    @modal.enter()
    def load_model(self):
        import os
        import sys
        import time

        sys.path.insert(0, "/root/MuseTalk")

        t0 = time.time()
        print("[MuseTalk] cold start begin", flush=True)

        # Ensure weights exist on volume (first run downloads ~10-15 GB)
        weights_dir = "/weights/musetalkV15"
        if not os.path.exists(weights_dir):
            print("[MuseTalk] weights missing, running download_weights.sh", flush=True)
            os.makedirs("/weights", exist_ok=True)
            # MuseTalk's own download script · pulls from HF + gdown
            os.system("cd /root/MuseTalk && bash download_weights.sh || true")
            os.system(f"cp -r /root/MuseTalk/models/* /weights/ 2>/dev/null || true")
            MUSETALK_VOLUME.commit()

        # Lazy import after weights ready
        from musetalk.utils.utils import load_all_model

        self.audio_processor, self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=f"{weights_dir}/unet.pth",
            unet_config=f"{weights_dir}/musetalk.json",
            device="cuda",
        )

        # Pre-cache Sophie reference landmarks if available
        self.sophie_landmark = None
        sophie_path = "/weights/assets/sophie-portrait-original.png"
        if os.path.exists(sophie_path):
            from musetalk.utils.preprocessing import get_landmark_and_bbox

            self.sophie_landmark, self.sophie_bbox = get_landmark_and_bbox(
                [sophie_path]
            )
            print("[MuseTalk] Sophie reference landmarks cached", flush=True)

        elapsed = round(time.time() - t0, 1)
        print(f"[MuseTalk] ready in {elapsed}s", flush=True)

    @modal.method()
    def warm(self):
        return {
            "status": "ready",
            "model": "MuseTalk v1.5",
            "license": "MIT (Lyra Lab/Tencent Music Entertainment)",
            "sophie_reference_cached": self.sophie_landmark is not None,
        }

    @modal.method()
    def generate_video_chunk(self, audio_pcm_bytes: bytes, fps: int = 25):
        """Inference one audio chunk (250-500ms) into video frames.

        Returns dict with H264-encoded video bytes ready to push down WS.
        """
        import io
        import soundfile as sf

        audio_arr, sr = sf.read(io.BytesIO(audio_pcm_bytes), dtype="float32")
        if sr != 16000:
            raise ValueError(f"Expected 16kHz PCM, got {sr}Hz")

        # NOTE: full datagen + blending + ffmpeg encoding pipeline
        # to be filled in by the next implementation pass.
        # MuseTalk scripts/realtime_inference.py is the reference.
        whisper_feature = self.audio_processor.audio2feature(audio_arr)

        return {
            "video_bytes": b"",  # TODO: encode H264 chunk
            "frame_count": 0,
            "fps": fps,
        }


# ---------------------------------------------------------------------------
# FastAPI ASGI app
# ---------------------------------------------------------------------------


@app.function(
    image=musetalk_image,
    secrets=[MUSETALK_AUTH_TOKEN_SECRET],
    timeout=900,
)
@modal.asgi_app()
def fastapi_app():
    import os

    from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File, Form
    from fastapi.responses import JSONResponse

    api = FastAPI(title="castle-voice-engine MuseTalk")
    runner = MuseTalkRunner()
    expected_token = os.environ.get("MUSETALK_AUTH_TOKEN", "")

    def _check_auth(authorization: str | None) -> None:
        if not expected_token:
            return  # dev mode
        if authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="invalid bearer")

    @api.get("/musetalk/health")
    async def health(authorization: str | None = None):
        _check_auth(authorization)
        info = runner.warm.remote()
        return info

    @api.post("/musetalk/enroll")
    async def enroll(
        image: UploadFile = File(...),
        subject: str = Form("speaker_unknown"),
        authorization: str | None = None,
    ):
        _check_auth(authorization)
        # Subject guard runs on the client side (musetalk_client.py).
        # Server-side defense-in-depth: re-check by re-importing rules.
        # (Skipped here to avoid pulling castle.safety into Modal image.
        #  Trust client + audit log on the server level.)
        contents = await image.read()
        # Persist into the weights volume so MuseTalkRunner can pick it up next cold start
        out_path = f"/weights/assets/{subject}.png"
        os.makedirs("/weights/assets", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(contents)
        MUSETALK_VOLUME.commit()
        return JSONResponse({"ok": True, "stored": out_path, "subject": subject})

    @api.websocket("/musetalk/stream")
    async def stream(ws: WebSocket):
        # NOTE: Modal does not yet expose websocket auth headers on
        # ws.headers in all SDK versions; relying on init frame token.
        await ws.accept()
        try:
            init = await ws.receive_json()
            if expected_token and init.get("auth") != expected_token:
                await ws.close(code=4401, reason="invalid bearer")
                return

            fps = int(init.get("fps", 25))
            subject = init.get("subject", "speaker_unknown")
            print(f"[MuseTalk WS] init subject={subject} fps={fps}", flush=True)

            while True:
                audio_bytes = await ws.receive_bytes()
                result = await runner.generate_video_chunk.remote.aio(
                    audio_bytes, fps=fps
                )
                if result["video_bytes"]:
                    await ws.send_bytes(result["video_bytes"])
        except Exception as e:
            print(f"[MuseTalk WS] closed: {e}", flush=True)
            try:
                await ws.close(code=1011, reason=str(e)[:120])
            except Exception:
                pass

    return api
