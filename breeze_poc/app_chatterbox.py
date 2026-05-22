# breeze_poc/app_chatterbox.py
# Voice Path v2.0 Phase 1 PoC - Chatterbox-Turbo (Resemble AI 官方)
# 2026-05-22 calcifer (5th TTS engine for Edward blind test)
# (c) 2026 Edward / BeyondPath. Apache-2.0 wrapper.
#
# Model: ResembleAI/chatterbox (Chatterbox-Turbo · MIT license · 0.5B Llama backbone)
# - Single-step decoder, ~350M effective inference path
# - Native zero-shot voice clone from short reference clip
# - Industry blind test: 63.75% prefer over ElevenLabs
# - Multilingual including zh
import modal

chatterbox_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git", "build-essential")
    # Install chatterbox-tts first so its hard pins (torch==2.6.0, transformers==5.2.0,
    # librosa==0.11.0, diffusers==0.29.0, etc.) drive the resolver. Then add extras.
    .pip_install("chatterbox-tts==0.1.7")
    .pip_install(
        "soundfile>=0.12",
        "huggingface_hub>=0.24",
        "scipy",
        "accelerate>=0.30",
    )
)

app = modal.App("chatterbox-poc")
AUTH_SECRET = modal.Secret.from_name("breeze-poc-auth")
HF_SECRET = modal.Secret.from_name("huggingface")


@app.cls(
    image=chatterbox_image,
    gpu="A10G",
    memory=16384,
    timeout=900,
    scaledown_window=300,
    secrets=[AUTH_SECRET, HF_SECRET],
    min_containers=0,
)
class ChatterboxTurbo:
    @modal.enter()
    def load_model(self):
        import time
        t0 = time.time()
        print("[Chatterbox] Cold start begin...")
        import torch
        # chatterbox-tts exposes ChatterboxTTS class which loads model on first init
        try:
            from chatterbox.tts import ChatterboxTTS
            self.runtime = "chatterbox_native"
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = ChatterboxTTS.from_pretrained(device=device)
            print("[Chatterbox] Loaded ChatterboxTTS in", round(time.time() - t0, 1), "s on", device)
        except Exception as e:
            print("[Chatterbox] native load fail:", str(e)[:500])
            raise
        print("[Chatterbox] Ready cold start:", round(time.time() - t0, 1), "s")

    @modal.method()
    def synthesize_with_voice(self, text: str, voice_prompt_bytes: bytes = None, voice_format: str = "mp3"):
        """
        Args:
          text: zh-TW text to synthesize
          voice_prompt_bytes: optional voice clone reference audio (mp3 or wav bytes)
          voice_format: 'mp3' or 'wav'
        Returns:
          dict with wav_bytes, sample_rate, latency_ms, etc.
        """
        import time, io, os, tempfile
        import torch
        import soundfile as sf
        import numpy as np
        import librosa
        t0 = time.time()

        # If voice prompt given, write to tmp file (chatterbox API takes audio_prompt_path)
        prompt_path = None
        prompt_dur = 0.0
        if voice_prompt_bytes:
            try:
                # Decode and normalize peak to 0.9 before writing
                voice_buf = io.BytesIO(voice_prompt_bytes)
                voice_array, voice_sr = librosa.load(voice_buf, sr=24000, mono=True)
                voice_array = voice_array.astype(np.float32)
                peak = float(np.max(np.abs(voice_array)))
                if peak > 0:
                    voice_array = voice_array * (0.9 / peak)
                prompt_dur = len(voice_array) / 24000
                # Write normalized prompt as wav to /tmp for chatterbox API
                fd, prompt_path = tempfile.mkstemp(suffix=".wav", prefix="chatterbox_prompt_")
                os.close(fd)
                sf.write(prompt_path, voice_array, 24000, subtype="PCM_16")
                print(f"[Chatterbox] voice prompt prepared: dur={prompt_dur:.2f}s peak_norm=0.9 path={prompt_path}")
            except Exception as e:
                print("[Chatterbox] voice prompt prep fail:", str(e)[:200])
                prompt_path = None
                prompt_dur = 0.0

        t_in = time.time()
        try:
            with torch.no_grad():
                if prompt_path:
                    wav = self.model.generate(text, audio_prompt_path=prompt_path)
                else:
                    wav = self.model.generate(text)
        except Exception as e:
            print("[Chatterbox] generate fail:", str(e)[:300])
            raise
        t_gen = time.time()

        # wav is torch.Tensor (1, samples) or (samples,) at self.model.sr
        try:
            if hasattr(wav, "cpu"):
                audio = wav.cpu().float().numpy()
            else:
                audio = np.asarray(wav, dtype=np.float32)
        except Exception as e:
            print("[Chatterbox] audio extract fail:", str(e)[:200])
            raise

        if audio.ndim > 1:
            audio = audio.squeeze()
        if audio.size < 100:
            raise RuntimeError("[Chatterbox] audio too small: size=" + str(audio.size))

        sr = int(getattr(self.model, "sr", 24000))

        # Normalize output to -1 dBFS peak (0.9 of fullscale)
        peak_out = float(np.max(np.abs(audio)))
        if peak_out > 0:
            audio = audio * (0.9 / peak_out)

        buf = io.BytesIO()
        sf.write(buf, audio, sr, subtype="PCM_16", format="WAV")
        wav_bytes = buf.getvalue()
        latency_ms = (time.time() - t0) * 1000

        # Cleanup tmp prompt
        if prompt_path and os.path.exists(prompt_path):
            try:
                os.remove(prompt_path)
            except Exception:
                pass

        return {
            "wav_bytes": wav_bytes,
            "sample_rate": sr,
            "latency_ms": round(latency_ms, 1),
            "inference_ms": round((t_gen - t_in) * 1000, 1),
            "text": text,
            "voice_ref": "edge-tts-zh-TW-HsiaoYuNeural-30s" if prompt_path else "chatterbox-default",
            "voice_clone_enabled": bool(prompt_path),
            "voice_prompt_duration_sec": round(prompt_dur, 2),
            "duration_sec": round(len(audio) / sr, 2),
        }
