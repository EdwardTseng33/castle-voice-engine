# breeze_poc/app_voxcpm2.py
# Voice Path v2.0 Phase 1 PoC - VoxCPM2 自然度測試
# 2026-05-22 calcifer (TTS A/B for Edward blind test)
# (c) 2026 Edward / BeyondPath. Apache-2.0
import modal

voxcpm2_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git", "build-essential")
    .pip_install(
        "torch>=2.5,<2.7",
        "torchaudio>=2.5,<2.7",
        "transformers>=4.45,<5.0",
        "accelerate>=0.30",
        "soundfile>=0.12",
        "librosa>=0.10",
        "huggingface_hub>=0.24",
        "numpy>=1.24,<2.0",
        "scipy",
        "fastapi>=0.110,<0.116",
        "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0",
        "python-multipart>=0.0.9",
        # VoxCPM dependency
        "voxcpm",
    )
)

app = modal.App("voxcpm2-poc")
AUTH_SECRET = modal.Secret.from_name("breeze-poc-auth")
HF_SECRET = modal.Secret.from_name("huggingface")


@app.cls(
    image=voxcpm2_image,
    gpu="A10G",
    memory=24576,
    timeout=900,
    scaledown_window=60,
    secrets=[AUTH_SECRET, HF_SECRET],
    min_containers=0,
)
class VoxCPM2:
    @modal.enter()
    def load_model(self):
        import time
        t0 = time.time()
        print("[VoxCPM2] Cold start begin...")
        from huggingface_hub import snapshot_download
        self.model_dir = snapshot_download(
            repo_id="openbmb/VoxCPM2",
            cache_dir="/root/models",
        )
        print("[VoxCPM2] snapshot_download done", round(time.time() - t0, 1), "s")
        try:
            from voxcpm import VoxCPM
            self.model = VoxCPM.from_pretrained(self.model_dir)
            self.runtime = "voxcpm_lib"
        except Exception as e:
            print("[VoxCPM2] voxcpm.from_pretrained fail:", str(e)[:300])
            # fallback: HF transformers
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor
            self.processor = AutoProcessor.from_pretrained(self.model_dir, trust_remote_code=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_dir, torch_dtype=torch.bfloat16, device_map="cuda",
                trust_remote_code=True,
            )
            self.model.eval()
            self.runtime = "transformers_fallback"
        print("[VoxCPM2] Ready", self.runtime, "cold start:", round(time.time() - t0, 1), "s")

    @modal.method()
    def synthesize(self, text: str):
        import time, io
        import numpy as np
        import soundfile as sf
        t0 = time.time()
        sr = 16000
        audio = None
        if self.runtime == "voxcpm_lib":
            # VoxCPM official API: model.generate(text=..., prompt_wav_path=None for default voice)
            try:
                audio = self.model.generate(
                    text=text,
                    prompt_wav_path=None,
                    prompt_text=None,
                    cfg_value=2.0,
                    inference_timesteps=10,
                    normalize=True,
                    denoise=True,
                    retry_badcase=True,
                    retry_badcase_max_times=3,
                )
            except TypeError:
                # older API
                audio = self.model.generate(text=text, cfg_value=2.0, inference_timesteps=10)
            if isinstance(audio, dict):
                audio = audio.get("audio", audio.get("wav", None))
            if hasattr(audio, "cpu"):
                audio = audio.cpu().float().numpy()
            if hasattr(audio, "squeeze"):
                audio = audio.squeeze()
            sr = getattr(self.model, "sample_rate", 16000)
        else:
            raise RuntimeError("VoxCPM2 transformers_fallback path not implemented in PoC")
        if audio is None or len(audio) < 100:
            raise RuntimeError("[VoxCPM2] empty audio output")
        if audio.ndim > 1:
            audio = audio.squeeze()
        buf = io.BytesIO()
        sf.write(buf, audio, sr, subtype="PCM_16", format="WAV")
        wav_bytes = buf.getvalue()
        latency_ms = (time.time() - t0) * 1000
        return {
            "wav_bytes": wav_bytes,
            "sample_rate": int(sr),
            "latency_ms": round(latency_ms, 1),
            "text": text,
            "duration_sec": round(len(audio) / sr, 2),
            "runtime": self.runtime,
        }


@app.function(
    image=modal.Image.debian_slim(python_version="3.11").pip_install(
        "fastapi>=0.110,<0.116", "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0", "python-multipart>=0.0.9"),
    cpu=2, memory=2048, timeout=900, scaledown_window=300,
    secrets=[AUTH_SECRET],
)
@modal.asgi_app()
def voxcpm2_api():
    import os
    from fastapi import FastAPI, HTTPException, Header, Form
    from fastapi.responses import Response, JSONResponse
    fastapi_app = FastAPI(title="voxcpm2-poc", version="0.1")

    def _check_auth(token):
        expected = os.environ.get("BREEZE_AUTH_TOKEN")
        if not token or token != expected:
            raise HTTPException(401, "auth failed")

    @fastapi_app.get("/health")
    def health():
        return {"ok": True, "app": "voxcpm2-poc"}

    @fastapi_app.post("/synthesize")
    async def synthesize(text: str = Form(...), x_auth_token = Header(default=None)):
        _check_auth(x_auth_token)
        if not text.strip():
            raise HTTPException(400, "text empty")
        vc = VoxCPM2()
        result = await vc.synthesize.remote.aio(text=text)
        wav = result.pop("wav_bytes")
        return Response(content=wav, media_type="audio/wav",
            headers={
                "X-TTS-Latency-Ms": str(result["latency_ms"]),
                "X-TTS-Sample-Rate": str(result["sample_rate"]),
                "X-TTS-Duration-Sec": str(result["duration_sec"]),
                "X-TTS-Runtime": str(result["runtime"]),
            })

    return fastapi_app
