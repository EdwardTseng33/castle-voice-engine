# scripts/tts_oneshot.py
# 一次性 TTS · 用 OpenAI gpt-4o-mini-tts (女聲 · 接近 Realtime marin)
# 用法:
#   modal run scripts/tts_oneshot.py --text "早安..." --out tts.mp3
# 不部署任何長期 endpoint · 跑完就結束

import modal

app = modal.App("castle-tts-oneshot")

image = modal.Image.debian_slim(python_version="3.11").pip_install("openai>=1.50")


@app.function(
    image=image,
    timeout=120,
    secrets=[modal.Secret.from_name("openai")],
)
def generate_tts(text: str, voice: str = "coral", instructions: str = "") -> bytes:
    import os
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # gpt-4o-mini-tts 支援 instructions 控制語氣 · 接近 Realtime marin
    kwargs = {
        "model": "gpt-4o-mini-tts",
        "voice": voice,
        "input": text,
        "response_format": "mp3",
    }
    if instructions:
        kwargs["instructions"] = instructions

    # OpenAI SDK >= 1.50 用 with_streaming_response 或直接呼 audio.speech.create
    resp = client.audio.speech.create(**kwargs)
    return resp.content


@app.local_entrypoint()
def main(text: str, out: str = "tts.mp3", voice: str = "coral", instructions: str = ""):
    if not instructions:
        # 蘇菲對長輩的口吻 · 溫暖 · 不急
        instructions = (
            "Speak in warm, gentle Taiwanese Mandarin with a caring, "
            "slightly soft and unhurried tone, like greeting an elderly aunt. "
            "Keep natural prosody, no robotic flatness."
        )
    audio_bytes = generate_tts.remote(text=text, voice=voice, instructions=instructions)
    with open(out, "wb") as f:
        f.write(audio_bytes)
    print(f"saved {len(audio_bytes)} bytes -> {out}")
