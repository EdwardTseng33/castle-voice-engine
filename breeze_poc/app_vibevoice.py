# breeze_poc/app_vibevoice.py
# Voice Path v2.0 Phase 1 PoC - VibeVoice 自然度測試
# 2026-05-22 calcifer (TTS A/B for Edward blind test)
# (c) 2026 Edward / BeyondPath. Apache-2.0
import modal

vibevoice_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git", "build-essential")
    .pip_install(
        "torch>=2.2,<2.5",
        "torchaudio>=2.2,<2.5",
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
    )
)

app = modal.App("vibevoice-poc")
AUTH_SECRET = modal.Secret.from_name("breeze-poc-auth")
HF_SECRET = modal.Secret.from_name("huggingface")


@app.cls(
    image=vibevoice_image,
    gpu="A10G",
    memory=24576,
    timeout=900,
    scaledown_window=60,
    secrets=[AUTH_SECRET, HF_SECRET],
    min_containers=0,
)
class VibeVoice:
    @modal.enter()
    def load_model(self):
        import time, os
        t0 = time.time()
        print("[VibeVoice] Cold start begin...")
        from huggingface_hub import snapshot_download
        self.model_dir = snapshot_download(
            repo_id="microsoft/VibeVoice-1.5B",
            cache_dir="/root/models",
        )
        print("[VibeVoice] snapshot_download done", round(time.time() - t0, 1), "s")
        # VibeVoice load via transformers VibeVoiceForConditionalGeneration
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor, AutoConfig
        # VibeVoice has custom code, trust_remote_code=True
        try:
            self.processor = AutoProcessor.from_pretrained(self.model_dir, trust_remote_code=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_dir,
                torch_dtype=torch.bfloat16,
                device_map="cuda",
                trust_remote_code=True,
                attn_implementation="sdpa",
            )
            self.model.eval()
            self.runtime = "transformers_auto"
            print("[VibeVoice] Loaded via AutoModelForCausalLM in", round(time.time() - t0, 1), "s")
        except Exception as e:
            print("[VibeVoice] AutoModelForCausalLM fail:", str(e)[:300])
            # Fallback: try VibeVoiceForConditionalGeneration directly
            from transformers import AutoModel
            self.processor = AutoProcessor.from_pretrained(self.model_dir, trust_remote_code=True)
            self.model = AutoModel.from_pretrained(
                self.model_dir,
                torch_dtype=torch.bfloat16,
                device_map="cuda",
                trust_remote_code=True,
            )
            self.model.eval()
            self.runtime = "transformers_automodel"
        print("[VibeVoice] Ready", self.runtime, "cold start:", round(time.time() - t0, 1), "s")

    @modal.method()
    def synthesize(self, text: str, speaker_id: int = 0):
        import time, io
        import torch
        import soundfile as sf
        import numpy as np
        t0 = time.time()
        # VibeVoice expects script format: "Speaker N: text"
        # Use VibeVoice native demo voice. Default speaker = "en-Alice" or built-in zh speaker
        # script format
        speaker_names = ["en-Alice_woman", "en-Carter_man", "in-Samuel_man", "zh-Bowen_man"]
        spk = speaker_names[speaker_id % len(speaker_names)]
        script = f"Speaker 0: {text}"
        # processor expects list of scripts + list of voice samples (paths)
        try:
            inputs = self.processor(
                text=[script],
                voice_samples=[[f"/root/.cache/vibevoice/demo/{spk}.wav"]],
                padding=True,
                return_tensors="pt",
            ).to("cuda")
        except Exception as e:
            print("[VibeVoice] processor without voice_samples...", str(e)[:200])
            inputs = self.processor(text=[script], padding=True, return_tensors="pt").to("cuda")
        t_in = time.time()
        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                max_new_tokens=4096,
                do_sample=False,
                cfg_scale=1.3,
                tokenizer=self.processor.tokenizer,
            )
        t_gen = time.time()
        # decode audio: VibeVoice returns audio in out.speech_outputs or via processor.batch_decode
        audio = None
        try:
            audio = out.speech_outputs[0].cpu().float().numpy()
        except Exception:
            try:
                audio = self.processor.batch_decode_audio(out)[0]
            except Exception as e:
                print("[VibeVoice] audio extract fail:", e)
        if audio is None or len(audio) < 100:
            raise RuntimeError("[VibeVoice] empty audio output")
        if audio.ndim > 1:
            audio = audio.squeeze()
        sr = 24000  # VibeVoice default
        buf = io.BytesIO()
        sf.write(buf, audio, sr, subtype="PCM_16", format="WAV")
        wav_bytes = buf.getvalue()
        latency_ms = (time.time() - t0) * 1000
        return {
            "wav_bytes": wav_bytes,
            "sample_rate": sr,
            "latency_ms": round(latency_ms, 1),
            "inference_ms": round((t_gen - t_in) * 1000, 1),
            "text": text,
            "speaker": spk,
            "duration_sec": round(len(audio) / sr, 2),
        }


@app.function(
    image=modal.Image.debian_slim(python_version="3.11").pip_install(
        "fastapi>=0.110,<0.116", "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0", "python-multipart>=0.0.9"),
    cpu=2, memory=2048, timeout=900, scaledown_window=300,
    secrets=[AUTH_SECRET],
)
@modal.asgi_app()
def vibevoice_api():
    import os
    from fastapi import FastAPI, HTTPException, Header, Form
    from fastapi.responses import Response, JSONResponse
    fastapi_app = FastAPI(title="vibevoice-poc", version="0.1")

    def _check_auth(token):
        expected = os.environ.get("BREEZE_AUTH_TOKEN")
        if not token or token != expected:
            raise HTTPException(401, "auth failed")

    @fastapi_app.get("/health")
    def health():
        return {"ok": True, "app": "vibevoice-poc"}

    @fastapi_app.post("/synthesize")
    async def synthesize(
        text: str = Form(...),
        speaker_id: int = Form(default=0),
        x_auth_token = Header(default=None),
    ):
        _check_auth(x_auth_token)
        if not text.strip():
            raise HTTPException(400, "text empty")
        vv = VibeVoice()
        result = await vv.synthesize.remote.aio(text=text, speaker_id=speaker_id)
        wav = result.pop("wav_bytes")
        return Response(content=wav, media_type="audio/wav",
            headers={
                "X-TTS-Latency-Ms": str(result["latency_ms"]),
                "X-TTS-Inference-Ms": str(result["inference_ms"]),
                "X-TTS-Sample-Rate": str(result["sample_rate"]),
                "X-TTS-Duration-Sec": str(result["duration_sec"]),
                "X-TTS-Speaker": str(result["speaker"]),
            })

    return fastapi_app
