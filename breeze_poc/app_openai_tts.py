# breeze_poc/app_openai_tts.py
# Voice Path v2.0 Phase 1 PoC - OpenAI gpt-4o-mini-tts
# 2026-05-22 calcifer · Edward compare OpenAI vs ElevenLabs · ship OpenAI first
# (c) 2026 Edward / BeyondPath. Apache-2.0 wrapper.
#
# Model: openai gpt-4o-mini-tts (released 2026-05-08)
# - 13 preset voices · NO voice clone (preset only)
# - Chinese particularly strong per OpenAI docs
# - Pricing: $0.015/min (cheapest in industry)
# - API: client.audio.speech.create(model='gpt-4o-mini-tts', voice=..., input=...)
# - Output: WAV (response_format='wav') · 24000 Hz default
#
# Modal deployment rationale
# - openai secret already in Modal (created 2026-04-28 by edwardt0303)
# - Local has no OPENAI_API_KEY · don't extract secret (sandbox blocks credential exfil · correctly)
# - Modal function handles TTS call + returns wav bytes to client
# - Cost-bound: ~10 min total audio for full run · $0.15 estimated · well under $1 cap
import modal

openai_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("openai>=1.50", "soundfile>=0.12", "numpy", "scipy")
)

app = modal.App("openai-tts-poc")
OPENAI_SECRET = modal.Secret.from_name("openai")


@app.cls(
    image=openai_image,
    cpu=2,
    memory=4096,
    timeout=300,
    scaledown_window=120,
    secrets=[OPENAI_SECRET],
    min_containers=0,
)
class OpenAITTS:
    @modal.enter()
    def setup(self):
        import os
        from openai import OpenAI
        # Modal openai secret stores OPENAI_API_KEY env var (standard convention)
        # Don't print or log the key · just consume it
        self.client = OpenAI()  # picks up OPENAI_API_KEY from env
        self.model = "gpt-4o-mini-tts"
        print(f"OpenAI client ready · model={self.model}")

    @modal.method()
    def synthesize(self, text: str, voice: str = "nova", instructions: str = "") -> dict:
        """Generate TTS and return wav bytes + metadata.

        Args:
            text: text to synthesize
            voice: one of alloy/ash/ballad/coral/echo/fable/nova/onyx/sage/shimmer/verse + 2 new
            instructions: optional steering prompt (gpt-4o-mini-tts supports this)

        Returns dict with:
            wav: bytes (WAV format, normalized to -1 dBFS)
            inference_ms: float
            input_chars: int
            voice: str
            sample_rate: int
        """
        import time
        import io
        import numpy as np
        import soundfile as sf

        t0 = time.time()
        kwargs = dict(
            model=self.model,
            voice=voice,
            input=text,
            response_format="wav",
        )
        if instructions:
            kwargs["instructions"] = instructions

        response = self.client.audio.speech.create(**kwargs)
        wav_bytes_raw = response.content
        inference_ms = (time.time() - t0) * 1000.0

        # Normalize to -1 dBFS peak (consistent with other PoC outputs)
        data, sr = sf.read(io.BytesIO(wav_bytes_raw), dtype="float32")
        peak = float(np.abs(data).max())
        if peak > 0:
            # -1 dBFS = 10^(-1/20) ≈ 0.8913
            target_peak = 10.0 ** (-1.0 / 20.0)
            scale = target_peak / peak
            data = data * scale

        # Re-encode to int16 WAV (consistent with chatterbox output)
        out_buf = io.BytesIO()
        sf.write(out_buf, data, sr, format="WAV", subtype="PCM_16")
        wav_bytes_norm = out_buf.getvalue()

        return {
            "wav": wav_bytes_norm,
            "inference_ms": round(inference_ms, 1),
            "input_chars": len(text),
            "voice": voice,
            "sample_rate": sr,
            "duration_sec": round(len(data) / sr, 2),
            "peak_pre_norm": round(peak, 4),
        }


@app.local_entrypoint()
def smoke():
    """Quick sanity test · 1 short sentence × 1 voice."""
    cls = OpenAITTS()
    result = cls.synthesize.remote(
        text="蘇菲在這裡，我們開始吧。",
        voice="nova",
    )
    print(f"smoke OK · voice=nova · inference_ms={result['inference_ms']} · "
          f"duration={result['duration_sec']}s · wav={len(result['wav'])} bytes")
