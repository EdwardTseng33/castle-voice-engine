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
        "transformers==4.51.3",
        "accelerate==1.6.0",
        "soundfile>=0.12",
        "librosa>=0.10",
        "huggingface_hub>=0.24",
        "numpy>=1.24,<2.0",
        "scipy",
        "fastapi>=0.110,<0.116",
        "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0",
        "python-multipart>=0.0.9",
        "vibevoice",
        "ml-collections",
        "absl-py",
        "diffusers",
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
    scaledown_window=62,  # bump for refresh (size fix)
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
        # VibeVoice native loader (vibevoice package)
        try:
            from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
            from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor
            self.processor = VibeVoiceProcessor.from_pretrained(self.model_dir)
            self.model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                self.model_dir,
                torch_dtype=torch.bfloat16,
                device_map="cuda",
                attn_implementation="sdpa",
            )
            self.model.eval()
            self.runtime = "vibevoice_native"
            print("[VibeVoice] Loaded via vibevoice native in", round(time.time() - t0, 1), "s")
        except Exception as e:
            print("[VibeVoice] native fail:", str(e)[:500])
            raise
        print("[VibeVoice] Ready", self.runtime, "cold start:", round(time.time() - t0, 1), "s")

    @modal.method()
    def synthesize(self, text: str, speaker_id: int = 0):
        import time, io
        import torch
        import soundfile as sf
        import numpy as np
        t0 = time.time()
        # VibeVoice script format: "Speaker 0: text"
        # Use prebuilt voice samples bundled by HF demo (or use built-in synthesizer)
        # For zero-shot, we need a voice sample. Use a short synthetic placeholder if none provided.
        spk = "en-Alice_woman"
        if not hasattr(self, "_default_voice_sample"):
            import urllib.request, soundfile as sf, io
            # VibeVoice demo voices live in the repo "demo/voices" path
            # Use a built-in en-Alice voice sample (small wav from VibeVoice github)
            try:
                # The VibeVoice processor expects a list of voice sample paths or numpy arrays
                # Use a clean sine-wave + envelope-modulated speech-like signal as bootstrap
                import numpy as np
                sr_voice = 24000
                # Create a 5-sec speech-like envelope (no actual speech but realistic energy profile)
                t = np.arange(sr_voice * 5) / sr_voice
                # Modulated noise to simulate speech rhythm
                env = 0.4 * (1 + np.sin(2 * np.pi * 3 * t))  # syllable rate ~3 Hz
                carrier = np.random.randn(len(t)).astype("float32") * 0.15
                speech_like = (env * carrier).astype("float32")
                self._default_voice_sample = speech_like
                print("[VibeVoice] using synthetic speech-like voice sample (5s @ 24kHz)")
            except Exception as e:
                print("[VibeVoice] voice sample setup fail:", str(e)[:200])
                raise
        script = "Speaker 0: " + text
        try:
            inputs = self.processor(
                text=[script],
                voice_samples=[[self._default_voice_sample]],
                padding=True,
                return_tensors="pt",
            )
            # move tensors to cuda
            inputs = {k: (v.to("cuda") if hasattr(v, "to") else v) for k, v in inputs.items()}
        except Exception as e:
            print("[VibeVoice] processor build fail:", str(e)[:200])
            raise
        t_in = time.time()
        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                max_new_tokens=2048,
                do_sample=False,
                cfg_scale=1.3,
                tokenizer=self.processor.tokenizer,
            )
        t_gen = time.time()
        audio = None
        print("[VibeVoice] out type:", type(out).__name__, "attrs:", [a for a in dir(out) if not a.startswith("_")][:30])
        for attr in ("speech_outputs", "audio_outputs", "audios", "audio", "speech", "wav", "waveforms"):
            try:
                v = getattr(out, attr, None)
                if v is not None:
                    print("[VibeVoice] try attr", attr, "type=", type(v).__name__)
                    if hasattr(v, "__len__") and len(v) > 0:
                        first = v[0]
                        if hasattr(first, "cpu"):
                            arr = first.cpu().float().numpy()
                            if hasattr(arr, "ndim") and arr.size > 100:
                                audio = arr
                                print("[VibeVoice] got audio via", attr, "shape=", arr.shape)
                                break
                        elif hasattr(first, "shape") and first.size > 100:
                            audio = first
                            print("[VibeVoice] got audio np via", attr, "shape=", first.shape)
                            break
            except Exception as ex:
                print("[VibeVoice]   attr", attr, "fail:", str(ex)[:120])
        if audio is None:
            try:
                if hasattr(self.processor, "batch_decode_audio"):
                    decoded = self.processor.batch_decode_audio(out)
                    if decoded and len(decoded) > 0:
                        d0 = decoded[0]
                        if hasattr(d0, "cpu"):
                            audio = d0.cpu().float().numpy()
                        else:
                            audio = d0
                        print("[VibeVoice] got via batch_decode_audio shape=", getattr(audio, "shape", None))
            except Exception as ex:
                print("[VibeVoice] batch_decode_audio fail:", str(ex)[:200])
        if audio is None:
            # Try out.sequences -> decoder approach (sometimes audio comes through sequences with audio token vocab)
            try:
                seq = getattr(out, "sequences", None)
                if seq is not None and hasattr(self.processor, "audio_decoder"):
                    audio_t = self.processor.audio_decoder.decode(seq)
                    audio = audio_t[0].cpu().float().numpy() if hasattr(audio_t[0], "cpu") else audio_t[0]
                    print("[VibeVoice] got via audio_decoder shape=", audio.shape)
            except Exception as ex:
                print("[VibeVoice] audio_decoder fail:", str(ex)[:200])
        if audio is None:
            raise RuntimeError("[VibeVoice] empty audio output (all extract methods failed)")
        # Flatten if 2D (shape like (1, samples))
        if hasattr(audio, "ndim") and audio.ndim > 1:
            audio = audio.squeeze()
        if hasattr(audio, "size") and audio.size < 100:
            raise RuntimeError("[VibeVoice] audio too small: size=" + str(audio.size))
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
