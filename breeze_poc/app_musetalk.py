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
        "librosa==0.11.0",  # Phase 6 (calcifer): MuseTalk audio_processor depends on librosa
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
        # Phase 5 fix (2026-05-23 calcifer): use sentinel file instead of dir exist check
        # because empty dir shells from failed previous downloads pass the os.path.exists check
        sentinel = "/weights/.muse_v15_complete"
        weights_ready = os.path.exists(sentinel)

        if not weights_ready:
            # Phase 6 (2026-05-23 calcifer): Python-native huggingface_hub snapshot_download
            # replaces broken download_weights.sh (silent-fail due to hf-mirror.com unreachable
            # from Modal US datacenters + huggingface-cli exit 0 on partial fail).
            # Reproduces every line of download_weights.sh in Python (6 HF repos + gdown + curl).
            print("[MuseTalk] weights sentinel missing, downloading via huggingface_hub", flush=True)
            os.makedirs("/weights", exist_ok=True)
            for sub in ("musetalk", "musetalkV15", "syncnet", "dwpose",
                        "face-parse-bisent", "sd-vae", "whisper"):
                os.makedirs(f"/weights/{sub}", exist_ok=True)

            from huggingface_hub import snapshot_download

            # 1) MuseTalk v1.0 + v1.5 (same repo, allow_patterns scopes the download)
            print("[MuseTalk] [1/6] TMElyralab/MuseTalk (musetalk/ + musetalkV15/)", flush=True)
            snapshot_download(
                repo_id="TMElyralab/MuseTalk",
                local_dir="/weights",
                allow_patterns=[
                    "musetalk/musetalk.json", "musetalk/pytorch_model.bin",
                    "musetalkV15/musetalk.json", "musetalkV15/unet.pth",
                ],
            )

            # 2) SD-VAE-ft-mse (config.json + diffusion_pytorch_model.bin)
            print("[MuseTalk] [2/6] stabilityai/sd-vae-ft-mse", flush=True)
            snapshot_download(
                repo_id="stabilityai/sd-vae-ft-mse",
                local_dir="/weights/sd-vae",
                allow_patterns=["config.json", "diffusion_pytorch_model.bin"],
            )

            # 3) Whisper-tiny (3 files for MuseTalk audio2feature path)
            print("[MuseTalk] [3/6] openai/whisper-tiny", flush=True)
            snapshot_download(
                repo_id="openai/whisper-tiny",
                local_dir="/weights/whisper",
                allow_patterns=["config.json", "pytorch_model.bin", "preprocessor_config.json"],
            )

            # 4) DWPose
            print("[MuseTalk] [4/6] yzd-v/DWPose", flush=True)
            snapshot_download(
                repo_id="yzd-v/DWPose",
                local_dir="/weights/dwpose",
                allow_patterns=["dw-ll_ucoco_384.pth"],
            )

            # 5) SyncNet (ByteDance/LatentSync)
            print("[MuseTalk] [5/6] ByteDance/LatentSync (syncnet)", flush=True)
            snapshot_download(
                repo_id="ByteDance/LatentSync",
                local_dir="/weights/syncnet",
                allow_patterns=["latentsync_syncnet.pt"],
            )

            # 6) Face-parse-bisent (gdown + resnet18 curl) -- non-HF sources
            import subprocess
            face_parse_target = "/weights/face-parse-bisent/79999_iter.pth"
            if not os.path.exists(face_parse_target):
                print("[MuseTalk] [6a/6] face-parse-bisent via gdown", flush=True)
                # gdown v5+ removed --id; use positional URL form (works both gdown v4 + v5)
                gd = subprocess.run(
                    ["gdown",
                     "https://drive.google.com/uc?id=154JgKpzCPW82qINcVieuPH3fZ2e0P812",
                     "-O", face_parse_target, "--no-cookies"],
                    capture_output=True, text=True, timeout=600,
                )
                if gd.returncode != 0:
                    print("[MuseTalk] gdown stderr:", gd.stderr[-800:], flush=True)
                    print("[MuseTalk] gdown stdout:", gd.stdout[-800:], flush=True)
                    raise RuntimeError(f"gdown face-parse-bisent failed rc={gd.returncode}")
                # Verify gdown actually downloaded a non-trivial file (defense against silent fail)
                if not os.path.exists(face_parse_target) or os.path.getsize(face_parse_target) < 10*1024*1024:
                    actual = os.path.getsize(face_parse_target) if os.path.exists(face_parse_target) else 0
                    print(f"[MuseTalk] gdown stdout:", gd.stdout[-800:], flush=True)
                    raise RuntimeError(f"gdown produced suspicious file size {actual} bytes (expected ~50MB)")
                print(f"[MuseTalk] gdown wrote {os.path.getsize(face_parse_target)/1024/1024:.1f} MB", flush=True)

            resnet_target = "/weights/face-parse-bisent/resnet18-5c106cde.pth"
            if not os.path.exists(resnet_target):
                # urllib.request beats subprocess curl - no apt rebuild + native to image python
                print("[MuseTalk] [6b/6] resnet18 via urllib from pytorch.org", flush=True)
                import urllib.request
                urllib.request.urlretrieve(
                    "https://download.pytorch.org/models/resnet18-5c106cde.pth",
                    resnet_target,
                )
                size_mb = os.path.getsize(resnet_target) / 1024 / 1024
                print(f"[MuseTalk] resnet18 downloaded {size_mb:.1f} MB", flush=True)

            # Diagnostic: list actual contents post-download
            for path in ["/weights"]:
                ls = subprocess.run(["ls", "-la", path], capture_output=True, text=True)
                print(f"[MuseTalk] DIAG ls {path}", flush=True)
                print(ls.stdout, flush=True)
                find = subprocess.run(
                    ["find", path, "-maxdepth", "3", "-type", "f", "-size", "+1k"],
                    capture_output=True, text=True,
                )
                print(f"[MuseTalk] DIAG files >1k under {path}", flush=True)
                print(find.stdout, flush=True)

            # Verify critical model files exist before sealing sentinel
            # (Phase 5 list + Phase 6 additions covering all 6 sources)
            critical = [
                "/weights/musetalkV15/unet.pth",
                "/weights/musetalkV15/musetalk.json",
                "/weights/sd-vae/config.json",
                "/weights/sd-vae/diffusion_pytorch_model.bin",
                "/weights/whisper/pytorch_model.bin",
                "/weights/whisper/config.json",
                "/weights/dwpose/dw-ll_ucoco_384.pth",
                "/weights/syncnet/latentsync_syncnet.pt",
                "/weights/face-parse-bisent/79999_iter.pth",
                "/weights/face-parse-bisent/resnet18-5c106cde.pth",
            ]
            missing = [p for p in critical if not os.path.exists(p)]
            if missing:
                raise RuntimeError(f"critical model files missing after download: {missing}")

            with open(sentinel, "w") as f:
                f.write("v15 download complete - calcifer phase 6 HF native - 2026-05-23")
            MUSETALK_VOLUME.commit()
            print("[MuseTalk] sentinel written + volume committed", flush=True)
        else:
            print("[MuseTalk] sentinel found, skip download", flush=True)

        # Critical: MuseTalk internal code uses hardcoded relative path "models/sd-vae"
        # So we must (a) chdir to /root/MuseTalk and (b) symlink /root/MuseTalk/models -> /weights
        if not os.path.lexists("/root/MuseTalk/models"):
            os.symlink("/weights", "/root/MuseTalk/models")
            print("[MuseTalk] symlink /root/MuseTalk/models -> /weights created", flush=True)
        elif os.path.islink("/root/MuseTalk/models"):
            print("[MuseTalk] symlink already in place", flush=True)
        else:
            # real dir from download_weights.sh exists, replace with symlink to volume
            import shutil
            shutil.rmtree("/root/MuseTalk/models")
            os.symlink("/weights", "/root/MuseTalk/models")
            print("[MuseTalk] replaced real dir with symlink -> /weights", flush=True)

        os.chdir("/root/MuseTalk")
        weights_dir = "/weights/musetalkV15"

        # Lazy import after weights ready
        # Phase 6 (2026-05-23): load_all_model returns 3 values (vae, unet, pe); audio_processor
        # is a separate class loaded from local whisper-tiny dir to avoid HF hub network call
        from musetalk.utils.utils import load_all_model
        from musetalk.utils.audio_processor import AudioProcessor

        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=f"{weights_dir}/unet.pth",
            unet_config=f"{weights_dir}/musetalk.json",
            device="cuda",
        )
        # AudioProcessor uses transformers AutoFeatureExtractor; point at local whisper dir
        self.audio_processor = AudioProcessor(feature_extractor_path="/weights/whisper")
        print("[MuseTalk] models loaded: vae + unet + pe + audio_processor", flush=True)

        # Pre-cache Sophie reference landmarks if available
        # Phase 6 (calcifer): lazy-load to avoid mmpose dep at cold start (mmpose
        # is huge + needs cuda; defer to first generate_video_chunk call).
        # health endpoint can return ready without landmark cache.
        self.sophie_landmark = None
        self.sophie_bbox = None
        sophie_path = "/weights/assets/sophie-portrait-original.png"
        if os.path.exists(sophie_path):
            try:
                from musetalk.utils.preprocessing import get_landmark_and_bbox
                self.sophie_landmark, self.sophie_bbox = get_landmark_and_bbox(
                    [sophie_path]
                )
                print("[MuseTalk] Sophie reference landmarks cached", flush=True)
            except ModuleNotFoundError as e:
                print(f"[MuseTalk] Sophie landmark deferred (missing dep: {e})", flush=True)
                # health endpoint will still report ready; first chunk inference will need mmpose

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

    from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File, Form, Header
    from fastapi.responses import JSONResponse

    api = FastAPI(title="castle-voice-engine MuseTalk")
    runner = MuseTalkRunner()
    expected_token = os.environ.get("MUSETALK_AUTH_TOKEN", "")

    # Server-side defense-in-depth for Sally hard rule (Gate 4 WARN-1 補強).
    # Client (castle/integrations/musetalk_client.py) already enforces subject_guard;
    # this inline set is the last line of defense in case any caller bypasses the client.
    # Keep in sync with castle/safety/subject_guard.py _DENIED_SUBJECTS.
    _SERVER_DENIED_SUBJECTS = frozenset({
        "sally", "minor", "child", "stranger", "visitor",
    })

    def _check_auth(authorization: str | None) -> None:
        if not expected_token:
            return  # dev mode
        if authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="invalid bearer")

    @api.get("/musetalk/health")
    async def health(authorization: str | None = Header(None)):
        _check_auth(authorization)
        info = runner.warm.remote()
        return info

    @api.post("/musetalk/enroll")
    async def enroll(
        image: UploadFile = File(...),
        subject: str = Form("speaker_unknown"),
        authorization: str | None = Header(None),
    ):
        _check_auth(authorization)
        # Server-side Sally hard rule defense-in-depth (Gate 4 WARN-1).
        # Client already passed subject_guard; this catches any bypass.
        subj_lower = (subject or "").strip().lower()
        if subj_lower in _SERVER_DENIED_SUBJECTS or not subj_lower:
            raise HTTPException(
                status_code=403,
                detail=f"subject={subj_lower!r} blocked by server-side hard rule",
            )
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
