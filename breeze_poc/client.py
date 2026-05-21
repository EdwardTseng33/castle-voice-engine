# breeze_poc/client.py - Day 3 client v2 (calcifer 5/22)
import os
import sys
import json
import pathlib
import uuid
import io
import urllib.request
import urllib.error

BREEZE_ENDPOINT = "https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run"


def _load_token():
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print("ERROR: .env not found at", env_path, file=sys.stderr)
        sys.exit(1)
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("BREEZE_AUTH_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip(chr(34)).strip(chr(39))
                if not tok:
                    print("ERROR: empty BREEZE_AUTH_TOKEN", file=sys.stderr)
                    sys.exit(1)
                return tok
    print("ERROR: BREEZE_AUTH_TOKEN not in .env", file=sys.stderr)
    sys.exit(1)


def _multipart_body(fields, files):
    boundary = "----CastleVoice" + uuid.uuid4().hex
    body = io.BytesIO()
    CRLF = "\r\n"
    for name, value in fields:
        body.write(("--" + boundary + CRLF).encode())
        body.write(("Content-Disposition: form-data; name=\"" + name + "\"" + CRLF + CRLF).encode())
        body.write(str(value).encode("utf-8"))
        body.write(CRLF.encode())
    for name, filename, file_bytes in files:
        body.write(("--" + boundary + CRLF).encode())
        body.write(("Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + filename + "\"" + CRLF).encode())
        body.write(("Content-Type: application/octet-stream" + CRLF + CRLF).encode())
        body.write(file_bytes)
        body.write(CRLF.encode())
    body.write(("--" + boundary + "--" + CRLF).encode())
    return body.getvalue(), boundary


def health():
    url = BREEZE_ENDPOINT + "/breeze/health?_cb=" + str(os.getpid())
    print("[health] GET", url)
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = json.loads(resp.read())
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data


def preprocess(input_path, output_path):
    token = _load_token()
    with open(input_path, "rb") as f:
        file_bytes = f.read()
    filename = pathlib.Path(input_path).name
    body, boundary = _multipart_body([], [("file", filename, file_bytes)])
    url = BREEZE_ENDPOINT + "/breeze/audio/preprocess"
    print("[preprocess] POST", url, len(file_bytes), "bytes ->", output_path)
    req = urllib.request.Request(
        url, data=body,
        headers={
            "X-Breeze-Token": token,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Content-Length": str(len(body)),
        }, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            wav = resp.read()
            with open(output_path, "wb") as f:
                f.write(wav)
            print("[preprocess] OK:", output_path, len(wav), "bytes")
            return wav
    except urllib.error.HTTPError as e:
        print("[preprocess] HTTP", e.code, e.read().decode()[:500], file=sys.stderr)
        sys.exit(1)


def transcribe(input_path, language="zh"):
    token = _load_token()
    with open(input_path, "rb") as f:
        file_bytes = f.read()
    filename = pathlib.Path(input_path).name
    body, boundary = _multipart_body(
        [("language", language)],
        [("file", filename, file_bytes)],
    )
    url = BREEZE_ENDPOINT + "/breeze/asr/transcribe"
    print("[transcribe] POST", url, len(file_bytes), "bytes lang=", language)
    req = urllib.request.Request(
        url, data=body,
        headers={
            "X-Breeze-Token": token,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Content-Length": str(len(body)),
        }, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return data
    except urllib.error.HTTPError as e:
        print("[transcribe] HTTP", e.code, e.read().decode()[:500], file=sys.stderr)
        sys.exit(1)


def synthesize(text, prompt_wav_path, output_path, prompt_text="hi"):
    token = _load_token()
    with open(prompt_wav_path, "rb") as f:
        prompt_bytes = f.read()
    prompt_filename = pathlib.Path(prompt_wav_path).name
    body, boundary = _multipart_body(
        [("text", text), ("prompt_text", prompt_text)],
        [("prompt_file", prompt_filename, prompt_bytes)],
    )
    url = BREEZE_ENDPOINT + "/breeze/tts/synthesize"
    print("[synthesize] POST", url, "text:", text[:50], "prompt:", prompt_filename, len(prompt_bytes), "bytes")
    req = urllib.request.Request(
        url, data=body,
        headers={
            "X-Breeze-Token": token,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Content-Length": str(len(body)),
        }, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            wav = resp.read()
            with open(output_path, "wb") as f:
                f.write(wav)
            meta = {
                "latency_ms": resp.headers.get("X-Breeze-TTS-Latency-Ms"),
                "inference_ms": resp.headers.get("X-Breeze-TTS-Inference-Ms"),
                "sample_rate": resp.headers.get("X-Breeze-TTS-Sample-Rate"),
                "duration_sec": resp.headers.get("X-Breeze-TTS-Duration-Sec"),
            }
            print("[synthesize] OK:", output_path, len(wav), "bytes")
            print(json.dumps(meta, indent=2, ensure_ascii=False))
            return wav, meta
    except urllib.error.HTTPError as e:
        print("[synthesize] HTTP", e.code, e.read().decode()[:500], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  py client.py health")
        print("  py client.py preprocess <input> <output.wav>")
        print("  py client.py transcribe <input> [--lang zh]")
        print("  py client.py synthesize <text> <prompt_wav> <output.wav> [--prompt_text X]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "health":
        health()
    elif cmd == "preprocess":
        if len(sys.argv) != 4:
            print("Usage: preprocess <input> <output.wav>"); sys.exit(1)
        preprocess(sys.argv[2], sys.argv[3])
    elif cmd == "transcribe":
        if len(sys.argv) < 3:
            print("Usage: transcribe <input> [--lang zh]"); sys.exit(1)
        lang = "zh"
        if "--lang" in sys.argv:
            lang = sys.argv[sys.argv.index("--lang") + 1]
        transcribe(sys.argv[2], language=lang)
    elif cmd == "synthesize":
        if len(sys.argv) < 5:
            print("Usage: synthesize <text> <prompt_wav> <output.wav> [--prompt_text X]"); sys.exit(1)
        prompt_text = "hi"
        if "--prompt_text" in sys.argv:
            prompt_text = sys.argv[sys.argv.index("--prompt_text") + 1]
        synthesize(sys.argv[2], sys.argv[3], sys.argv[4], prompt_text=prompt_text)
    else:
        print("Unknown command:", cmd); sys.exit(1)
