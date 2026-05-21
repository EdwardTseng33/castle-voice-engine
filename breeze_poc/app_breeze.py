# breeze_poc/app_breeze.py
# Voice Path v2.0 Phase 1 PoC - Breeze stack
# Day 3 (5/22 calcifer auto): real Breeze-ASR-25 GPU + BreezyVoice TTS GPU
# (c) 2026 Edward / BeyondPath. Apache-2.0
import modal

breeze_cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi>=0.110,<0.116",
        "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0",
        "python-multipart>=0.0.9",
    )
)

breeze_asr_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git")
    .pip_install(
        "torch>=2.1,<2.5",
        "transformers>=4.40,<5.0",
        "soundfile>=0.12",
        "librosa>=0.10",
        "jiwer>=3.0",
        "accelerate>=0.30",
        "huggingface_hub>=0.20",
    )
)

breeze_tts_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git", "wget", "sox", "libsox-dev", "build-essential")
    .pip_install("setuptools<70", "wheel", "pip>=24")
    # Aligned with BreezyVoice upstream requirements.txt
    .pip_install("openai-whisper")  # latest wheel, has whisper package
    .pip_install(
        "torch==2.3.1",
        "torchaudio==2.3.1",
        "transformers>=4.40,<5.0",
        "soundfile==0.12.1",
        "librosa==0.10.2",
        "huggingface_hub>=0.20",
        "onnxruntime-gpu==1.16.0",
        "numpy>=1.24,<2.0",
        "scipy",
        "HyperPyYAML==1.2.2",
        "ruamel.yaml<0.18",
        "modelscope",
        "pyyaml",
        "tqdm",
        "diffusers==0.32.0",
        "omegaconf==2.3.0",
        "gdown==5.1.0",
        "pyarrow",
        "matplotlib==3.7.5",
        "wget==3.2",
        "WeTextProcessing==1.0.3",
        "lightning==2.2.4",
        "ruamel.yaml<0.18",
        "hydra-core==1.3.2",
        "networkx==3.1",
        "pydantic==2.7.0",
        "rich",
    )
    # Legacy build-isolation deps
    .run_commands(
        "echo day3_v4 && pip install --no-build-isolation conformer==0.3.2 inflect==7.3.1 opencc-python-reimplemented",
        "pip install g2pw==0.1.1",
        "pip install --no-build-isolation openai-whisper==20231117 || pip install --no-build-isolation openai-whisper==20240930 || echo whisper_skip",
        # BreezyVoice repo includes Matcha-TTS as third_party submodule
        "cd /root && git clone --recurse-submodules https://github.com/mtkresearch/BreezyVoice.git || (cd /root && git clone https://github.com/mtkresearch/BreezyVoice.git && cd BreezyVoice && git submodule update --init --recursive)",
        # Fallback: clone Matcha-TTS standalone if submodule path empty
        "ls /root/BreezyVoice/third_party/Matcha-TTS/matcha 2>/dev/null || (mkdir -p /root/BreezyVoice/third_party && cd /root/BreezyVoice/third_party && git clone https://github.com/shivammehta25/Matcha-TTS.git)",
    )
)

app = modal.App("castle-voice-engine-breeze-poc")
BREEZE_AUTH_TOKEN_SECRET = modal.Secret.from_name("breeze-poc-auth")
HF_SECRET = modal.Secret.from_name("huggingface")


@app.cls(
    image=breeze_asr_image,
    gpu="A10G",
    memory=16384,
    timeout=600,
    scaledown_window=60,
    secrets=[BREEZE_AUTH_TOKEN_SECRET, HF_SECRET],
    min_containers=0,
)
class BreezeASR:
    @modal.enter()
    def load_model(self):
        import torch
        from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
        print("[BreezeASR] Loading MediaTek-Research/Breeze-ASR-25...")
        model_id = "MediaTek-Research/Breeze-ASR-25"
        try:
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_id, torch_dtype=torch.float16, low_cpu_mem_usage=True,
            )
            self.model_id = model_id
        except Exception as e:
            print("[BreezeASR] ASR-25 failed:", e, "fallback to ASR-26")
            model_id = "MediaTek-Research/Breeze-ASR-26"
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_id, torch_dtype=torch.float16, low_cpu_mem_usage=True,
            )
            self.model_id = model_id
        self.model = self.model.to("cuda")
        self.model.eval()
        print("[BreezeASR] Loaded", self.model_id, "-> CUDA fp16")

    @modal.method()
    def transcribe(self, wav_bytes, language="zh"):
        import io, time
        import torch
        import soundfile as sf
        t0 = time.time()
        audio_arr, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        if sr != 16000:
            raise ValueError("Expected 16kHz got " + str(sr))
        if audio_arr.ndim > 1:
            audio_arr = audio_arr.mean(axis=1)
        t_load = time.time()
        if len(audio_arr) / sr > 30:
            print("[BreezeASR] truncating to 30s")
            audio_arr = audio_arr[: 30 * sr]
        inputs = self.processor(audio_arr, sampling_rate=16000, return_tensors="pt")
        input_features = inputs.input_features.to("cuda").to(torch.float16)
        forced_decoder_ids = self.processor.get_decoder_prompt_ids(
            language=language, task="transcribe"
        )
        t_prep = time.time()
        with torch.no_grad():
            generated = self.model.generate(
                input_features,
                forced_decoder_ids=forced_decoder_ids,
                max_new_tokens=440,
            )
        t_inference = time.time()
        text = self.processor.batch_decode(generated, skip_special_tokens=True)[0].strip()
        t_decode = time.time()
        latency_ms = (t_decode - t0) * 1000
        print("[BreezeASR] e2e_ms=", round(latency_ms, 1), "text=", text[:50])
        return {
            "text": text,
            "latency_ms": round(latency_ms, 1),
            "breakdown_ms": {
                "audio_load": round((t_load - t0) * 1000, 1),
                "preprocessing": round((t_prep - t_load) * 1000, 1),
                "inference": round((t_inference - t_prep) * 1000, 1),
                "decode": round((t_decode - t_inference) * 1000, 1),
            },
            "model": self.model_id,
            "language": language,
            "audio_duration_sec": round(len(audio_arr) / sr, 2),
        }


@app.cls(
    image=breeze_tts_image,
    gpu="A10G",
    memory=24576,
    timeout=900,
    scaledown_window=121,  # bump to force new class container
    secrets=[BREEZE_AUTH_TOKEN_SECRET, HF_SECRET],
    min_containers=0,
)
class BreezyVoiceTTS:
    @modal.enter()
    def load_model(self):
        import os, sys, time
        from huggingface_hub import snapshot_download
        t0 = time.time()
        print("[BreezyVoiceTTS] Cold start begin...")
        sys.path.insert(0, "/root/BreezyVoice")
        third_party = "/root/BreezyVoice/third_party/Matcha-TTS"
        if os.path.exists(third_party):
            sys.path.insert(0, third_party)
        print("[BreezyVoiceTTS] Downloading model from HF...")
        self.model_dir = snapshot_download(
            repo_id="MediaTek-Research/BreezyVoice",
            cache_dir="/root/models",
        )
        print("[BreezyVoiceTTS] Model dir:", self.model_dir, "took", round(time.time() - t0, 1), "s")
        runtime_err = []
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice
            self.cosyvoice = CosyVoice(self.model_dir)
            self.runtime = "cosyvoice_cli"
        except Exception as e:
            runtime_err.append("cosyvoice_cli: " + str(e))
            try:
                from single_inference import CustomCosyVoice
                self.cosyvoice = CustomCosyVoice(self.model_dir)
                self.runtime = "breezyvoice_custom"
            except Exception as e2:
                runtime_err.append("breezyvoice_custom: " + str(e2))
                raise RuntimeError("BreezyVoice runtime init failed: " + str(runtime_err))
        print("[BreezyVoiceTTS] Ready", self.runtime, "cold start:", round(time.time() - t0, 1), "s")

    @modal.method()
    def synthesize(self, text, prompt_wav_bytes, prompt_text="hi"):
        import io, time
        import soundfile as sf
        import torch
        t0 = time.time()
        audio_arr, sr = sf.read(io.BytesIO(prompt_wav_bytes), dtype="float32")
        if audio_arr.ndim > 1:
            audio_arr = audio_arr.mean(axis=1)
        prompt_tensor = torch.from_numpy(audio_arr).unsqueeze(0).float()
        t_load = time.time()
        # Both runtimes provide inference_zero_shot. CustomCosyVoice returns dict, CosyVoice cli returns iterator/dict varies by version.
        result = self.cosyvoice.inference_zero_shot(text, prompt_text or "hi", prompt_tensor)
        if isinstance(result, dict):
            output_tensor = result["tts_speech"]
        else:
            chunks = [c["tts_speech"] for c in result]
            output_tensor = torch.cat(chunks, dim=1)
        output_sr = getattr(self.cosyvoice, "sample_rate", 22050)
        t_inference = time.time()
        output_np = output_tensor.squeeze().cpu().numpy()
        if output_np.ndim > 1:
            output_np = output_np.squeeze()
        buf = io.BytesIO()
        sf.write(buf, output_np, output_sr, subtype="PCM_16", format="WAV")
        wav_bytes = buf.getvalue()
        latency_ms = (time.time() - t0) * 1000
        print("[BreezyVoiceTTS] text_len=", len(text), "total_ms=", round(latency_ms, 1))
        return {
            "wav_bytes": wav_bytes,
            "sample_rate": output_sr,
            "latency_ms": round(latency_ms, 1),
            "breakdown_ms": {
                "prompt_load": round((t_load - t0) * 1000, 1),
                "inference": round((t_inference - t_load) * 1000, 1),
            },
            "text": text,
            "output_duration_sec": round(len(output_np) / output_sr, 2),
        }


@app.function(
    image=breeze_cpu_image,
    cpu=2,
    memory=2048,
    timeout=900,
    scaledown_window=300,
    secrets=[BREEZE_AUTH_TOKEN_SECRET],
)
@modal.asgi_app()
def breeze_fastapi():
    import os, tempfile, subprocess, time
    from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Form
    from fastapi.responses import Response, JSONResponse
    fastapi_app = FastAPI(
        title="castle-voice-engine-breeze-poc",
        version="0.3.1-day3-async-fix",
    )
    AUTH_TOKEN = os.environ.get("BREEZE_AUTH_TOKEN", "")

    def _check_auth(x_breeze_token):
        if not AUTH_TOKEN:
            raise HTTPException(503, "BREEZE_AUTH_TOKEN secret not set")
        if x_breeze_token != AUTH_TOKEN:
            raise HTTPException(401, "Edward personal token rejected")

    def _preprocess_to_16k_wav(raw_bytes):
        with tempfile.NamedTemporaryFile(suffix=".input", delete=False) as in_tmp:
            in_tmp.write(raw_bytes)
            in_tmp.flush()
            in_path = in_tmp.name
        out_path = in_path + ".wav"
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", in_path,
                 "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                raise HTTPException(500, "ffmpeg failed: " + result.stderr.decode()[:500])
            with open(out_path, "rb") as f:
                return f.read()
        finally:
            for p in (in_path, out_path):
                try:
                    os.remove(p)
                except OSError:
                    pass

    @fastapi_app.get("/breeze/health")
    def health():
        return {
            "status": "ok",
            "version": "0.3.1-day3-fix",
            "day": 3,
            "stack": "breeze",
            "models": {
                "asr": "MediaTek-Research/Breeze-ASR-25 (auto-fallback ASR-26)",
                "tts": "MediaTek-Research/BreezyVoice (voice cloning)",
            },
            "isolation_check": {
                "modal_volume_attached": False,
                "audio_persisted": False,
            },
        }

    @fastapi_app.post("/breeze/audio/preprocess")
    async def preprocess_audio(
        file: UploadFile = File(...),
        x_breeze_token = Header(default=None),
    ):
        _check_auth(x_breeze_token)
        raw = await file.read()
        if len(raw) == 0:
            raise HTTPException(400, "empty file")
        if len(raw) > 50 * 1024 * 1024:
            raise HTTPException(413, "too large " + str(len(raw)))
        wav_bytes = _preprocess_to_16k_wav(raw)
        print("[breeze.preprocess] input=", len(raw), "output=", len(wav_bytes))
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "X-Breeze-Sample-Rate": "16000",
                "X-Breeze-Channels": "1",
                "X-Breeze-Privacy": "ephemeral-no-volume-persist",
            },
        )

    @fastapi_app.post("/breeze/asr/transcribe")
    async def transcribe_audio(
        file: UploadFile = File(...),
        language: str = Form(default="zh"),
        x_breeze_token = Header(default=None),
    ):
        _check_auth(x_breeze_token)
        raw = await file.read()
        if len(raw) == 0:
            raise HTTPException(400, "empty file")
        if len(raw) > 50 * 1024 * 1024:
            raise HTTPException(413, "too large " + str(len(raw)))
        t_pp_start = time.time()
        wav_bytes = _preprocess_to_16k_wav(raw)
        t_pp_end = time.time()
        asr = BreezeASR()
        result = await asr.transcribe.remote.aio(wav_bytes, language=language)
        result["preprocess_ms"] = round((t_pp_end - t_pp_start) * 1000, 1)
        result["total_e2e_ms"] = round(result["preprocess_ms"] + result["latency_ms"], 1)
        return JSONResponse(content=result)

    @fastapi_app.post("/breeze/tts/synthesize")
    async def synthesize_speech(
        text: str = Form(...),
        prompt_file: UploadFile = File(...),
        prompt_text: str = Form(default="hi"),
        x_breeze_token = Header(default=None),
    ):
        _check_auth(x_breeze_token)
        if not text.strip():
            raise HTTPException(400, "text empty")
        prompt_raw = await prompt_file.read()
        if len(prompt_raw) == 0:
            raise HTTPException(400, "prompt_file empty")
        prompt_wav = _preprocess_to_16k_wav(prompt_raw)
        tts = BreezyVoiceTTS()
        result = await tts.synthesize.remote.aio(text=text, prompt_wav_bytes=prompt_wav, prompt_text=prompt_text)
        wav_bytes = result.pop("wav_bytes")
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "X-Breeze-TTS-Latency-Ms": str(result["latency_ms"]),
                "X-Breeze-TTS-Inference-Ms": str(result["breakdown_ms"]["inference"]),
                "X-Breeze-TTS-Sample-Rate": str(result["sample_rate"]),
                "X-Breeze-TTS-Duration-Sec": str(result["output_duration_sec"]),
                "X-Breeze-Privacy": "ephemeral-no-volume-persist",
            },
        )

    return fastapi_app


@app.local_entrypoint()
def smoke():
    import urllib.request, json
    url = breeze_fastapi.get_web_url() + "breeze/health"
    print("[smoke] GET", url)
    with urllib.request.urlopen(url) as resp:
        print("[smoke]", json.dumps(json.loads(resp.read()), indent=2, ensure_ascii=False))
