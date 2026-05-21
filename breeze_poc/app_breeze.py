# breeze_poc/app_breeze.py
# Voice Path v2.0 Phase 1 PoC · Breeze stack 並存試做 (Day 1 skeleton)
# (c) 2026 Edward / BeyondPath. Apache-2.0 (Breeze-ASR-25 / BreezyVoice 基底)
#
# 隔離原則 (Gate 5 條件 1+5):
#   - 跟現役 app.py 並存、不衝突 (modal app name 不同 / route prefix /breeze/*)
#   - 聲音檔 never 進 Modal Volume (用 tempfile + bytes in memory)
#   - PoC 期間僅 Edward 個人 token 限定
#
# Day 1 endpoint:
#   POST /breeze/audio/preprocess   - m4a/wav input -> WAV 16kHz mono bytes
#                                     (Eagle / Breeze-ASR 標準輸入格式)
#
# Day 2+ 加入:
#   POST /breeze/asr/transcribe     - Breeze-ASR-25 中文轉文字
#   POST /breeze/tts/synthesize     - BreezyVoice 中文女聲合成
#   POST /breeze/eagle/enroll       - Picovoice Eagle 聲紋註冊
#   POST /breeze/eagle/verify       - 聲紋認證
#   POST /breeze/chat/converse      - Llama-Breeze2 + Sophie persona + function calling

from __future__ import annotations

import modal

# A10G image with ffmpeg + torch + transformers
# (ffmpeg 走 apt-get、不污染 Edward 本機 PATH)
breeze_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        # Day 1 base
        "fastapi>=0.110,<0.116",
        "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0",
        # Day 2 ASR/TTS (預載、Day 1 暫不用、但 image 一次 build 完省 cold start)
        "torch>=2.1,<2.5",
        "transformers>=4.40",
        "soundfile>=0.12",
        "librosa>=0.10",
        # Day 5 Eagle (Picovoice 商用 SDK · PoC 用個人版 KEY)
        # "pveagle>=1.0",   # 留 Day 5 開啟、Day 1 先不裝、image 輕一點
    )
    .add_local_dir("../castle", remote_path="/root/castle")
)

# 第二個 Modal App、跟現役 castle-voice-engine 並存、不衝突
app = modal.App("castle-voice-engine-breeze-poc")

# Edward 個人 token 環境變數 (Gate 5 條件 5)
BREEZE_AUTH_TOKEN_SECRET = modal.Secret.from_name(
    "breeze-poc-auth",
    # 若 secret 不存在、deploy 會報、Edward 手動 create:
    #   modal secret create breeze-poc-auth BREEZE_AUTH_TOKEN=$(openssl rand -hex 32)
)


@app.function(
    image=breeze_image,
    cpu=2,                  # Day 1 audio preprocess CPU 夠
    memory=2048,
    timeout=120,
    scaledown_window=60,    # idle 1 分 scale-to-zero (省錢)
    secrets=[BREEZE_AUTH_TOKEN_SECRET],
)
@modal.asgi_app()
def breeze_fastapi():
    """
    Modal ASGI entry point.
    所有 /breeze/* 路由都掛在這個 function 底下。
    跟現役 fastapi_app (OpenAI Realtime) 完全隔離。
    """
    import os
    import tempfile
    import subprocess
    from fastapi import FastAPI, UploadFile, File, HTTPException, Header
    from fastapi.responses import Response

    fastapi_app = FastAPI(
        title="castle-voice-engine-breeze-poc",
        version="0.1.0-day1",
        description="Voice Path v2.0 Breeze stack PoC (並存試做、非 production)",
    )

    AUTH_TOKEN = os.environ.get("BREEZE_AUTH_TOKEN", "")

    def _check_auth(x_breeze_token: str | None):
        if not AUTH_TOKEN:
            raise HTTPException(503, "BREEZE_AUTH_TOKEN secret 未設定")
        if x_breeze_token != AUTH_TOKEN:
            raise HTTPException(401, "Edward 個人 token 不符 / 拒絕")

    @fastapi_app.get("/breeze/health")
    def health():
        return {
            "status": "ok",
            "version": "0.1.0-day1",
            "day": 1,
            "stack": "breeze",
            "note": "ffmpeg / pydub / torch 已安裝、ASR/TTS 待 Day 2 接上",
            "isolation_check": {
                "modal_volume_attached": False,  # Gate 5 條件 1
                "audio_persisted": False,
            },
        }

    @fastapi_app.post("/breeze/audio/preprocess")
    async def preprocess_audio(
        file: UploadFile = File(...),
        x_breeze_token: str | None = Header(default=None),
    ):
        """
        輸入 m4a / wav / 任何 ffmpeg 認的格式
        輸出 WAV 16kHz mono PCM 16-bit (Eagle / Breeze-ASR 標準)

        隱私鐵律 (Gate 5 條件 1):
          - 用 tempfile.NamedTemporaryFile (delete=True、function 結束 auto unlink)
          - 不寫 Volume
          - return bytes、function teardown 後 memory GC
        """
        _check_auth(x_breeze_token)

        raw = await file.read()
        if len(raw) == 0:
            raise HTTPException(400, "空檔")
        if len(raw) > 50 * 1024 * 1024:  # 50 MB 上限 (個人聲紋樣本不該超過)
            raise HTTPException(413, f"檔太大 {len(raw)} bytes、上限 50 MB")

        # tempfile auto-cleanup
        with tempfile.NamedTemporaryFile(suffix=".input", delete=True) as in_tmp:
            in_tmp.write(raw)
            in_tmp.flush()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as out_tmp:
                # ffmpeg 轉 WAV 16kHz mono 16-bit PCM (Eagle 標準)
                result = subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", in_tmp.name,
                        "-ar", "16000",      # 16 kHz
                        "-ac", "1",          # mono
                        "-c:a", "pcm_s16le", # 16-bit PCM little endian
                        out_tmp.name,
                    ],
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    raise HTTPException(
                        500,
                        f"ffmpeg 轉檔失敗: {result.stderr.decode()[:500]}",
                    )

                wav_bytes = out_tmp.read()

        # 顯式提醒 audio purged (debug 用、production 不留 log)
        print(f"[breeze.preprocess] input={len(raw)}B output={len(wav_bytes)}B (audio purged after return)")

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "X-Breeze-Sample-Rate": "16000",
                "X-Breeze-Channels": "1",
                "X-Breeze-Bits": "16",
                "X-Breeze-Privacy": "ephemeral-no-volume-persist",
            },
        )

    return fastapi_app


# Local entrypoint: deploy 後 smoke test
@app.local_entrypoint()
def smoke():
    """deploy 後跑 `modal run breeze_poc/app_breeze.py` 確認 /health 通"""
    import urllib.request
    import json
    url = breeze_fastapi.get_web_url() + "breeze/health"
    print(f"[smoke] GET {url}")
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
        print("[smoke] health:", json.dumps(data, indent=2, ensure_ascii=False))
