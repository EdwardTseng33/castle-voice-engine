# breeze_poc/app_chatterbox_mtl.py
# Voice Path v2.0 Phase 1 PoC - Chatterbox-Multilingual (Resemble AI 官方)
# 2026-05-22 calcifer · 5/22 上版用了 base (English-only) model · 本檔重跑修正
# (c) 2026 Edward / BeyondPath. Apache-2.0 wrapper.
#
# CORRECTION CONTEXT
# - 5/22 上版 app_chatterbox.py 用 `from chatterbox.tts import ChatterboxTTS`
#   = base model · English ONLY · 餵中文文字 = 英文人硬讀中文音節 · Edward 抓到
# - 本檔改用 `from chatterbox.mtl_tts import ChatterboxMultilingualTTS`
#   = 23-language multilingual · 含中文 (zh) · 必填 language_id 參數
# - 23 languages: ar/da/de/el/en/es/fi/fr/he/hi/it/ja/ko/ms/nl/no/pl/pt/ru/sv/sw/tr/zh
#
# Model: ResembleAI/chatterbox (Chatterbox-Multilingual class · same HF repo · MIT license)
# - chatterbox-tts==0.1.7 pkg ships both `chatterbox/tts.py` (base) and `chatterbox/mtl_tts.py` (MTL)
# - MTL `generate(text, language_id, audio_prompt_path=...)` · language_id is REQUIRED positional arg
# - Voice ref: 沿用 edge-xiaoyu-sophie-prompt.mp3 (中文 ref 配 zh language_id 是匹配的)
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

# Separate app name from base (chatterbox-poc) to avoid endpoint collision
app = modal.App("chatterbox-mtl-poc")
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
class ChatterboxMultilingual:
    @modal.enter()
    def load_model(self):
        import time
        t0 = time.time()
        print("[Chatterbox-MTL] Cold start begin...")
        import torch
        # ChatterboxMultilingualTTS - 23 lang including zh
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            self.runtime = "chatterbox_multilingual"
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = ChatterboxMultilingualTTS.from_pretrained(device=device)
            print("[Chatterbox-MTL] Loaded ChatterboxMultilingualTTS in",
                  round(time.time() - t0, 1), "s on", device)
            # Sanity: print supported langs to confirm zh present
            try:
                langs = self.model.get_supported_languages() if hasattr(self.model, "get_supported_languages") else None
                print("[Chatterbox-MTL] supported langs:", langs)
            except Exception:
                pass
        except Exception as e:
            print("[Chatterbox-MTL] native load fail:", str(e)[:500])
            raise
        print("[Chatterbox-MTL] Ready cold start:", round(time.time() - t0, 1), "s")

    @modal.method()
    def synthesize_with_voice(self, text: str, voice_prompt_bytes: bytes = None,
                              voice_format: str = "mp3", language_id: str = "zh"):
        """
        Args:
          text: text to synthesize (must match language_id)
          voice_prompt_bytes: optional voice clone reference audio (mp3 or wav bytes)
          voice_format: 'mp3' or 'wav'
          language_id: ISO lang code · default 'zh' for this correction run
        Returns:
          dict with wav_bytes, sample_rate, latency_ms, etc.
        """
        import time, io, os, tempfile
        import torch
        import soundfile as sf
        import numpy as np
        import librosa
        t0 = time.time()

        # If voice prompt given, write to tmp file (chatterbox MTL API takes audio_prompt_path)
        prompt_path = None
        prompt_dur = 0.0
        if voice_prompt_bytes:
            try:
                voice_buf = io.BytesIO(voice_prompt_bytes)
                voice_array, voice_sr = librosa.load(voice_buf, sr=24000, mono=True)
                voice_array = voice_array.astype(np.float32)
                peak = float(np.max(np.abs(voice_array)))
                if peak > 0:
                    voice_array = voice_array * (0.9 / peak)
                prompt_dur = len(voice_array) / 24000
                fd, prompt_path = tempfile.mkstemp(suffix=".wav", prefix="chatterbox_mtl_prompt_")
                os.close(fd)
                sf.write(prompt_path, voice_array, 24000, subtype="PCM_16")
                print(f"[Chatterbox-MTL] voice prompt prepared: dur={prompt_dur:.2f}s peak_norm=0.9 path={prompt_path}")
            except Exception as e:
                print("[Chatterbox-MTL] voice prompt prep fail:", str(e)[:200])
                prompt_path = None
                prompt_dur = 0.0

        t_in = time.time()
        try:
            with torch.no_grad():
                # MTL API: generate(text, language_id, audio_prompt_path=..., ...)
                # language_id is REQUIRED positional arg (not kwarg-optional like base)
                if prompt_path:
                    wav = self.model.generate(text, language_id, audio_prompt_path=prompt_path)
                else:
                    wav = self.model.generate(text, language_id)
        except Exception as e:
            print("[Chatterbox-MTL] generate fail:", str(e)[:300])
            raise
        t_gen = time.time()

        # wav is torch.Tensor (1, samples) or (samples,) at self.model.sr
        try:
            if hasattr(wav, "cpu"):
                audio = wav.cpu().float().numpy()
            else:
                audio = np.asarray(wav, dtype=np.float32)
        except Exception as e:
            print("[Chatterbox-MTL] audio extract fail:", str(e)[:200])
            raise

        if audio.ndim > 1:
            audio = audio.squeeze()
        if audio.size < 100:
            raise RuntimeError("[Chatterbox-MTL] audio too small: size=" + str(audio.size))

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
            "language_id": language_id,
            "model_class": "ChatterboxMultilingualTTS",
            "voice_ref": "edge-tts-zh-TW-HsiaoYuNeural-30s" if prompt_path else "chatterbox-default",
            "voice_clone_enabled": bool(prompt_path),
            "voice_prompt_duration_sec": round(prompt_dur, 2),
            "duration_sec": round(len(audio) / sr, 2),
        }
