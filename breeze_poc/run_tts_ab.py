import io, json, time, pathlib, uuid, urllib.request, urllib.error, sys
ROOT = pathlib.Path("C:/Users/Administrator/Claude/castle-voice-engine")
POC_RESULTS = ROOT / "breeze_poc" / "phase1-poc" / "results" / "tts-natural-ab"
SENT_PATH = POC_RESULTS / "sentences.txt"
TOKEN = None
with open(ROOT / ".env", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line.startswith("BREEZE_AUTH_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip().strip(chr(34)).strip(chr(39))
            break
print("Token loaded:", bool(TOKEN))
sentences = []
with open(SENT_PATH, "r", encoding="utf-8") as f:
    for line in f:
        s = line.rstrip()
        if s and not s.startswith("#"):
            sentences.append(s)
print("Loaded", len(sentences), "sentences")
DQ = chr(34)

def mp_post(url, fields, files, headers, timeout=600):
    boundary = "----CastleTTSAB" + uuid.uuid4().hex
    body = io.BytesIO()
    CRLF = b"\r\n"
    for k, v in fields.items():
        body.write(("--" + boundary).encode()); body.write(CRLF)
        body.write(("Content-Disposition: form-data; name=" + DQ + k + DQ).encode()); body.write(CRLF); body.write(CRLF)
        body.write(v.encode("utf-8")); body.write(CRLF)
    for fname, filename, content in files:
        body.write(("--" + boundary).encode()); body.write(CRLF)
        body.write(("Content-Disposition: form-data; name=" + DQ + fname + DQ + "; filename=" + DQ + filename + DQ).encode()); body.write(CRLF)
        body.write(b"Content-Type: application/octet-stream"); body.write(CRLF); body.write(CRLF)
        body.write(content); body.write(CRLF)
    body.write(("--" + boundary + "--").encode()); body.write(CRLF)
    data = body.getvalue()
    h = dict(headers)
    h["Content-Type"] = "multipart/form-data; boundary=" + boundary
    h["Content-Length"] = str(len(data))
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "body": resp.read(), "headers": dict(resp.headers), "status": resp.status, "client_total_ms": round((time.time() - t0) * 1000, 1)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": e.read().decode("utf-8", errors="replace")[:500], "client_total_ms": round((time.time() - t0) * 1000, 1)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "client_total_ms": round((time.time() - t0) * 1000, 1)}

def _save(meta, latencies, out_dir, name):
    if latencies:
        latencies.sort()
        n = len(latencies)
        meta["latency_p50_ms"] = round(latencies[n//2], 1)
        meta["latency_p95_ms"] = round(latencies[min(n-1, int(n*0.95))], 1)
        meta["latency_mean_ms"] = round(sum(latencies)/n, 1)
        meta["success_count"] = len(latencies)
    else:
        meta["success_count"] = 0
    with open(out_dir / "metadata.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    print(name, "done.", meta.get("success_count", 0), "/", len(sentences), "P50=", meta.get("latency_p50_ms"), "P95=", meta.get("latency_p95_ms"))

def run_vibevoice(endpoint_url):
    out_dir = POC_RESULTS / "vibevoice"
    out_dir.mkdir(exist_ok=True)
    meta = {"model": "Microsoft VibeVoice-1.5B", "model_version": "microsoft/VibeVoice-1.5B", "voice_profile": "demo speaker (en-Alice / built-in)", "voice_clone": "yes (zero-shot built-in speakers; default used here)", "deployment": "Modal A10G GPU, vibevoice-poc app", "license": "MIT (model) + Apache-2.0 (wrapper)", "endpoint": endpoint_url, "samples": []}
    latencies = []
    for i, s in enumerate(sentences, 1):
        idx = "t" + str(i).zfill(2)
        print("  [vibevoice " + idx + "] sending...")
        url = endpoint_url + "/synthesize"
        r = mp_post(url, fields={"text": s, "speaker_id": "0"}, files=[], headers={"X-Auth-Token": TOKEN}, timeout=600)
        if r["ok"]:
            outpath = out_dir / (idx + ".wav")
            with open(outpath, "wb") as fh: fh.write(r["body"])
            lat_ms = float(r["headers"].get("X-TTS-Latency-Ms", r["client_total_ms"]))
            latencies.append(lat_ms)
            meta["samples"].append({"id": idx, "text": s, "file": outpath.name, "latency_ms": lat_ms, "client_total_ms": r["client_total_ms"], "sample_rate": int(r["headers"].get("X-TTS-Sample-Rate", 24000)), "duration_sec": float(r["headers"].get("X-TTS-Duration-Sec", 0)), "speaker": r["headers"].get("X-TTS-Speaker", "")})
            print("    OK", round(lat_ms), "ms ->", outpath.name)
        else:
            print("    FAIL status=", r.get("status"), "err=", str(r.get("error", ""))[:200])
            meta["samples"].append({"id": idx, "text": s, "error": str(r.get("error", "")), "status": r.get("status")})
    _save(meta, latencies, out_dir, "vibevoice")

def run_voxcpm2(endpoint_url):
    out_dir = POC_RESULTS / "voxcpm2"
    out_dir.mkdir(exist_ok=True)
    meta = {"model": "OpenBMB VoxCPM2", "model_version": "openbmb/VoxCPM2", "voice_profile": "default voice (no prompt_wav)", "voice_clone": "yes (zero-shot if prompt_wav given; default used here)", "deployment": "Modal A10G GPU, voxcpm2-poc app", "license": "Apache-2.0 (model) + Apache-2.0 (wrapper)", "endpoint": endpoint_url, "samples": []}
    latencies = []
    for i, s in enumerate(sentences, 1):
        idx = "t" + str(i).zfill(2)
        print("  [voxcpm2 " + idx + "] sending...")
        url = endpoint_url + "/synthesize"
        r = mp_post(url, fields={"text": s}, files=[], headers={"X-Auth-Token": TOKEN}, timeout=600)
        if r["ok"]:
            outpath = out_dir / (idx + ".wav")
            with open(outpath, "wb") as fh: fh.write(r["body"])
            lat_ms = float(r["headers"].get("X-TTS-Latency-Ms", r["client_total_ms"]))
            latencies.append(lat_ms)
            meta["samples"].append({"id": idx, "text": s, "file": outpath.name, "latency_ms": lat_ms, "client_total_ms": r["client_total_ms"], "sample_rate": int(r["headers"].get("X-TTS-Sample-Rate", 16000)), "duration_sec": float(r["headers"].get("X-TTS-Duration-Sec", 0))})
            print("    OK", round(lat_ms), "ms ->", outpath.name)
        else:
            print("    FAIL status=", r.get("status"), "err=", str(r.get("error", ""))[:200])
            meta["samples"].append({"id": idx, "text": s, "error": str(r.get("error", "")), "status": r.get("status")})
    _save(meta, latencies, out_dir, "voxcpm2")

def run_breezyvoice_fixed(endpoint_url):
    out_dir = POC_RESULTS / "breezyvoice-fixed"
    out_dir.mkdir(exist_ok=True)
    prompt_wav_path = ROOT / "breeze_poc" / "phase1-poc" / "audio" / "edward_8s_prompt.wav"
    if not prompt_wav_path.exists():
        prompt_wav_path = ROOT / "breeze_poc" / "phase1-poc" / "audio" / "edward_voice_clone_demo.wav"
    with open(prompt_wav_path, "rb") as fh: prompt_wav_bytes = fh.read()
    print("  Using prompt:", prompt_wav_path.name, "(", len(prompt_wav_bytes), "bytes)")
    meta = {"model": "MediaTek BreezyVoice entry fixed: no_normalize + g2pw bopomofo prefix", "model_version": "MediaTek-Research/BreezyVoice via CustomCosyVoice runtime", "voice_profile": "voice clone from " + prompt_wav_path.name + " (Edward voice prompt)", "voice_clone": "yes (zero-shot prompt voice clone)", "deployment": "Modal A10G GPU, castle-voice-engine-breeze-poc app", "license": "Apache-2.0 (model) + Apache-2.0 (wrapper)", "fix_notes": ["Day 3 used wrong entry inference_zero_shot which normalizes and strips tones", "Day 4 fixed using inference_zero_shot_no_normalize + g2pw bopomofo prefix"], "endpoint": endpoint_url, "samples": []}
    latencies = []
    for i, s in enumerate(sentences, 1):
        idx = "t" + str(i).zfill(2)
        print("  [breezyvoice " + idx + "] sending...")
        if endpoint_url.endswith("/"): url = endpoint_url + "breeze/tts/synthesize"
        else: url = endpoint_url + "/breeze/tts/synthesize"
        r = mp_post(url, fields={"text": s, "prompt_text": "Hope this round sounds more natural"}, files=[("prompt_file", "prompt.wav", prompt_wav_bytes)], headers={"X-Breeze-Token": TOKEN}, timeout=600)
        if r["ok"]:
            outpath = out_dir / (idx + ".wav")
            with open(outpath, "wb") as fh: fh.write(r["body"])
            lat_ms = float(r["headers"].get("X-Breeze-TTS-Latency-Ms", r["client_total_ms"]))
            latencies.append(lat_ms)
            meta["samples"].append({"id": idx, "text": s, "file": outpath.name, "latency_ms": lat_ms, "client_total_ms": r["client_total_ms"], "sample_rate": int(r["headers"].get("X-Breeze-TTS-Sample-Rate", 22050)), "duration_sec": float(r["headers"].get("X-Breeze-TTS-Duration-Sec", 0)), "inference_ms": float(r["headers"].get("X-Breeze-TTS-Inference-Ms", 0))})
            print("    OK", round(lat_ms), "ms ->", outpath.name)
        else:
            print("    FAIL status=", r.get("status"), "err=", str(r.get("error", ""))[:200])
            meta["samples"].append({"id": idx, "text": s, "error": str(r.get("error", "")), "status": r.get("status")})
    _save(meta, latencies, out_dir, "breezyvoice")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    endpoint_map = {"vibevoice": "https://edwardt0303--vibevoice-poc-vibevoice-api.modal.run", "voxcpm2": "https://edwardt0303--voxcpm2-poc-voxcpm2-api.modal.run", "breezyvoice": "https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run/"}
    if target in ("vibevoice", "all"): run_vibevoice(endpoint_map["vibevoice"])
    if target in ("voxcpm2", "all"): run_voxcpm2(endpoint_map["voxcpm2"])
    if target in ("breezyvoice", "all"): run_breezyvoice_fixed(endpoint_map["breezyvoice"])
