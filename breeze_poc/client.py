# breeze_poc/client.py - 本機 client、卡西法 / Edward 跑 PoC 端點測試用
# 自動從 castle-voice-engine/.env 載 BREEZE_AUTH_TOKEN

import os
import sys
import pathlib
import json
import urllib.request
import urllib.error

BREEZE_ENDPOINT = "https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run"

def _load_token():
    """從 .env 讀 BREEZE_AUTH_TOKEN、不依賴外部 dotenv 套件"""
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print(f"ERROR: {env_path} 不存在。請複製 .env.example → .env 並填 BREEZE_AUTH_TOKEN", file=sys.stderr)
        sys.exit(1)
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("BREEZE_AUTH_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                if not token:
                    print(f"ERROR: .env 內 BREEZE_AUTH_TOKEN 是空值", file=sys.stderr)
                    sys.exit(1)
                return token
    print(f"ERROR: .env 內找不到 BREEZE_AUTH_TOKEN 行", file=sys.stderr)
    sys.exit(1)


def health():
    """GET /breeze/health - 不需 token"""
    url = f"{BREEZE_ENDPOINT}/breeze/health"
    print(f"[health] GET {url}")
    with urllib.request.urlopen(url, timeout=90) as resp:
        data = json.loads(resp.read())
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data


def preprocess(input_path, output_path):
    """POST /breeze/audio/preprocess - 需 token、m4a → WAV 16kHz mono"""
    token = _load_token()
    import io
    import uuid

    # 自製 multipart/form-data body（不用 requests 套件、純 stdlib）
    boundary = f"----CastleVoice{uuid.uuid4().hex}"
    with open(input_path, "rb") as f:
        file_bytes = f.read()
    filename = pathlib.Path(input_path).name
    
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.write(b"Content-Type: application/octet-stream\r\n\r\n")
    body.write(file_bytes)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    body_bytes = body.getvalue()

    url = f"{BREEZE_ENDPOINT}/breeze/audio/preprocess"
    print(f"[preprocess] POST {url}")
    print(f"           input: {input_path} ({len(file_bytes)} bytes)")
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={
            "X-Breeze-Token": token,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body_bytes)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            wav = resp.read()
            with open(output_path, "wb") as f:
                f.write(wav)
            print(f"[preprocess] OK: {output_path} ({len(wav)} bytes)")
            print(f"           Sample-Rate: {resp.headers.get('X-Breeze-Sample-Rate')}")
            print(f"           Channels: {resp.headers.get('X-Breeze-Channels')}")
            print(f"           Privacy: {resp.headers.get('X-Breeze-Privacy')}")
            return wav
    except urllib.error.HTTPError as e:
        print(f"[preprocess] HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  py breeze_poc/client.py health")
        print("  py breeze_poc/client.py preprocess <input.m4a> <output.wav>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "health":
        health()
    elif cmd == "preprocess":
        if len(sys.argv) != 4:
            print("Usage: preprocess <input.m4a> <output.wav>")
            sys.exit(1)
        preprocess(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
