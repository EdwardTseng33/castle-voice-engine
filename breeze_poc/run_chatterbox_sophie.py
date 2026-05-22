# breeze_poc/run_chatterbox_sophie.py
# Voice Path v2.0 Phase 1 PoC - Chatterbox-Turbo driver
# 2026-05-22 calcifer · narrow test · 10 sentences with Edge-Xiaoyu voice prompt
import json, pathlib, time, sys
ROOT = pathlib.Path("C:/Users/Administrator/Claude/castle-voice-engine")
RESULTS = ROOT / "breeze_poc" / "phase1-poc" / "results" / "tts-natural-ab"
SENT_PATH = RESULTS / "sentences.txt"
PROMPT_PATH = RESULTS / "sophie-voice-prompts" / "edge-xiaoyu-sophie-prompt.mp3"
OUT_DIR = RESULTS / "chatterbox-turbo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Load sentences (skip # comments)
sentences = []
with open(SENT_PATH, "r", encoding="utf-8") as f:
    for line in f:
        s = line.rstrip()
        if s and not s.startswith("#"):
            sentences.append(s)
print("Loaded", len(sentences), "sentences from", SENT_PATH)

# Load voice prompt bytes
with open(PROMPT_PATH, "rb") as f:
    prompt_bytes = f.read()
print("Loaded voice prompt:", PROMPT_PATH.name, "(", len(prompt_bytes), "bytes )")

# Import deployed Modal class
import modal
ChatterboxTurbo = modal.Cls.from_name("chatterbox-poc", "ChatterboxTurbo")
cls = ChatterboxTurbo()

meta = {
    "model": "Resemble AI Chatterbox-Turbo",
    "model_version": "ResembleAI/chatterbox (chatterbox-tts==0.1.7)",
    "model_size": "0.5B Llama backbone, ~350M single-step decoder path",
    "deployment": "Modal A10G GPU, chatterbox-poc app, edwardt0303 namespace",
    "voice_ref_source": "Azure Edge TTS zh-TW-HsiaoYuNeural (曉雨, same as VibeVoice-Sophie)",
    "voice_ref_file": "../sophie-voice-prompts/edge-xiaoyu-sophie-prompt.mp3",
    "voice_ref_duration_sec": 30,
    "voice_clone": "zero-shot from prompt mp3 (native Chatterbox API)",
    "normalize_target": "-1 dBFS peak (0.9 of int16 max, built into Modal endpoint)",
    "endpoint": "Modal class direct call (no HTTP)",
    "license": "MIT (Chatterbox model + chatterbox-tts pkg) + Apache-2.0 (wrapper) + Azure TTS terms for voice ref",
    "ship_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
    "ship_session": "calcifer 5/22 Chatterbox-Turbo narrow test (5th TTS engine)",
    "industry_blind_test_claim": "63.75% prefer over ElevenLabs (per Resemble AI)",
    "samples": [],
}

latencies = []
inference_times = []
for i, text in enumerate(sentences, 1):
    idx = "t" + str(i).zfill(2)
    out_wav = OUT_DIR / (idx + ".wav")
    print(f"\n[{idx}] '{text}'")
    t0 = time.time()
    try:
        result = cls.synthesize_with_voice.remote(
            text=text,
            voice_prompt_bytes=prompt_bytes,
            voice_format="mp3",
        )
        client_total_ms = round((time.time() - t0) * 1000, 1)
        wav_bytes = result["wav_bytes"]
        with open(out_wav, "wb") as fh:
            fh.write(wav_bytes)
        latencies.append(result["latency_ms"])
        inference_times.append(result["inference_ms"])
        sample_entry = {
            "id": idx,
            "text": text,
            "file": out_wav.name,
            "latency_ms": result["latency_ms"],
            "inference_ms": result["inference_ms"],
            "client_total_ms": client_total_ms,
            "duration_sec": result["duration_sec"],
            "sample_rate": result["sample_rate"],
            "voice_ref": result["voice_ref"],
            "voice_clone_enabled": result["voice_clone_enabled"],
            "voice_prompt_duration_sec": result["voice_prompt_duration_sec"],
        }
        meta["samples"].append(sample_entry)
        print(f"  OK lat={result['latency_ms']}ms inf={result['inference_ms']}ms dur={result['duration_sec']}s sr={result['sample_rate']} clone={result['voice_clone_enabled']} -> {out_wav.name}")
    except Exception as e:
        client_total_ms = round((time.time() - t0) * 1000, 1)
        err = str(e)[:500]
        print(f"  FAIL after {client_total_ms}ms: {err}")
        meta["samples"].append({
            "id": idx,
            "text": text,
            "error": err,
            "client_total_ms": client_total_ms,
        })

# P50/P95
if latencies:
    latencies.sort()
    n = len(latencies)
    meta["latency_p50_ms"] = round(latencies[n // 2], 1)
    meta["latency_p95_ms"] = round(latencies[min(n - 1, int(n * 0.95))], 1)
    meta["latency_mean_ms"] = round(sum(latencies) / n, 1)
    meta["success_count"] = len(latencies)
else:
    meta["success_count"] = 0
if inference_times:
    inference_times.sort()
    n = len(inference_times)
    meta["inference_p50_ms"] = round(inference_times[n // 2], 1)
    meta["inference_mean_ms"] = round(sum(inference_times) / n, 1)

with open(OUT_DIR / "metadata.json", "w", encoding="utf-8") as fh:
    json.dump(meta, fh, indent=2, ensure_ascii=False)
print(f"\nDone. {meta['success_count']}/{len(sentences)} ok. P50={meta.get('latency_p50_ms')}ms P95={meta.get('latency_p95_ms')}ms")
print("metadata:", OUT_DIR / "metadata.json")
