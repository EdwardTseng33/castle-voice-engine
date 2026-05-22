# breeze_poc/app_vibevoice_sophie.py
# Voice Path v2.0 Phase 1 PoC - VibeVoice + Edge TTS 曉雨 voice clone
# 2026-05-22 calcifer (Step 2 of Sophie-voice re-run, after race condition resolved)
# (c) 2026 Edward / BeyondPath. Apache-2.0
#
# Difference from app_vibevoice.py:
#   - Accepts voice_prompt_bytes (mp3 OR wav) instead of synthetic noise
#   - Modal-side decode via librosa @ 24kHz mono
#   - Use Edge TTS HsiaoYu sample as Sophie voice reference
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

app = modal.App("vibevoice-sophie")
AUTH_SECRET = modal.Secret.from_name("breeze-poc-auth")
HF_SECRET = modal.Secret.from_name("huggingface")


@app.cls(
    image=vibevoice_image,
    gpu="A10G",
    memory=24576,
    timeout=900,
    scaledown_window=300,
    secrets=[AUTH_SECRET, HF_SECRET],
    min_containers=0,
)
class VibeVoiceSophie:
    @modal.enter()
    def load_model(self):
        import time
        t0 = time.time()
        print("[VV-Sophie] Cold start begin...")
        from huggingface_hub import snapshot_download
        self.model_dir = snapshot_download(
            repo_id="microsoft/VibeVoice-1.5B",
            cache_dir="/root/models",
        )
        print("[VV-Sophie] snapshot_download done", round(time.time() - t0, 1), "s")
        import torch
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
            print("[VV-Sophie] Loaded vibevoice native in", round(time.time() - t0, 1), "s")
        except Exception as e:
            print("[VV-Sophie] native fail:", str(e)[:500])
            raise
        print("[VV-Sophie] Ready cold start:", round(time.time() - t0, 1), "s")

    @modal.method()
    def synthesize_with_voice(self, text: str, voice_prompt_bytes: bytes, voice_format: str = "mp3"):
        """
        Args:
          text: zh-TW text to synthesize
          voice_prompt_bytes: voice clone reference audio (mp3 or wav bytes)
          voice_format: 'mp3' or 'wav'
        """
        import time, io
        import torch
        import soundfile as sf
        import numpy as np
        import librosa
        t0 = time.time()

        # Decode voice prompt → numpy float32 @ 24kHz mono
        try:
            voice_buf = io.BytesIO(voice_prompt_bytes)
            voice_array, voice_sr = librosa.load(voice_buf, sr=24000, mono=True)
            voice_array = voice_array.astype(np.float32)
            # Normalize peak to 0.9
            peak = float(np.max(np.abs(voice_array)))
            if peak > 0:
                voice_array = voice_array * (0.9 / peak)
            print(f"[VV-Sophie] voice prompt decoded: sr={voice_sr} samples={len(voice_array)} dur={len(voice_array)/24000:.2f}s peak_after_norm={float(np.max(np.abs(voice_array))):.4f}")
        except Exception as e:
            print("[VV-Sophie] voice decode fail:", str(e)[:200])
            raise

        script = "Speaker 0: " + text
        try:
            inputs = self.processor(
                text=[script],
                voice_samples=[[voice_array]],
                padding=True,
                return_tensors="pt",
            )
            inputs = {k: (v.to("cuda") if hasattr(v, "to") else v) for k, v in inputs.items()}
        except Exception as e:
            print("[VV-Sophie] processor build fail:", str(e)[:300])
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

        # Extract audio
        audio = None
        for attr in ("speech_outputs", "audio_outputs", "audios", "audio", "speech", "wav", "waveforms"):
            try:
                v = getattr(out, attr, None)
                if v is not None and hasattr(v, "__len__") and len(v) > 0:
                    first = v[0]
                    if hasattr(first, "cpu"):
                        arr = first.cpu().float().numpy()
                        if hasattr(arr, "ndim") and arr.size > 100:
                            audio = arr
                            print(f"[VV-Sophie] got audio via {attr} shape={arr.shape}")
                            break
                    elif hasattr(first, "shape") and first.size > 100:
                        audio = first
                        break
            except Exception:
                pass
        if audio is None:
            try:
                if hasattr(self.processor, "batch_decode_audio"):
                    decoded = self.processor.batch_decode_audio(out)
                    if decoded and len(decoded) > 0:
                        d0 = decoded[0]
                        audio = d0.cpu().float().numpy() if hasattr(d0, "cpu") else d0
                        print(f"[VV-Sophie] got via batch_decode_audio shape={audio.shape}")
            except Exception as ex:
                print("[VV-Sophie] batch_decode_audio fail:", str(ex)[:200])
        if audio is None:
            raise RuntimeError("[VV-Sophie] empty audio output")

        if hasattr(audio, "ndim") and audio.ndim > 1:
            audio = audio.squeeze()
        if hasattr(audio, "size") and audio.size < 100:
            raise RuntimeError("[VV-Sophie] audio too small: size=" + str(audio.size))
        sr = 24000
        # Normalize output to -1 dBFS peak
        peak_out = float(np.max(np.abs(audio)))
        if peak_out > 0:
            audio = audio * (0.9 / peak_out)
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
            "voice_ref": "edge-tts-zh-TW-HsiaoYuNeural-30s",
            "duration_sec": round(len(audio) / sr, 2),
        }
