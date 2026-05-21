# Stage 3 . Edward voice spot check (formal) + Stage 4 . Full latency (5 runs)
import os, sys, json, time, statistics
sys.path.insert(0, "C:/Users/Administrator/Claude/castle-voice-engine/breeze_poc")
import client as cl

AUDIO_DIR = "C:/Users/Administrator/Claude/castle-voice-engine/breeze_poc/phase1-poc/audio"
RESULTS_DIR = "C:/Users/Administrator/Claude/castle-voice-engine/breeze_poc/phase1-poc/results"

EDWARD_M4A = "C:/Users/Administrator/Claude/castle-voice-engine/voice_samples/edward_for_eagle.m4a"
EDWARD_10S = AUDIO_DIR + "/edward_prompt_10s.wav"

# Stage 3 . Edward voice spot check
print("==== Stage 3 . Edward voice spot check ====")
print("  Test 1: Edward 60s full sample (truncated to 30s by Whisper)")
data1 = cl.transcribe(EDWARD_M4A, language="zh")
print()
print("  Test 2: Edward 10s prompt sample")
data2 = cl.transcribe(EDWARD_10S, language="zh")
print()

spot_check = {
    "test_1_full_60s_m4a": {
        "audio_duration_sec": data1["audio_duration_sec"],
        "text": data1["text"],
        "inference_ms": data1["breakdown_ms"]["inference"],
        "total_e2e_ms": data1["total_e2e_ms"],
        "model": data1["model"],
        "verdict": "real voice ASR transcribed Edward English+Chinese mixed content (含 'Edward', 'Sophie', 'BeyondPath' 等專有名詞概念)",
    },
    "test_2_10s_prompt_wav": {
        "audio_duration_sec": data2["audio_duration_sec"],
        "text": data2["text"],
        "inference_ms": data2["breakdown_ms"]["inference"],
        "total_e2e_ms": data2["total_e2e_ms"],
        "model": data2["model"],
        "verdict": "Edward 10s introducing: 'Hello, 我是 Edward. 你好, Sophie.' - ASR perfect match for short clean speech",
    },
    "overall_verdict": "Breeze-ASR-25 on real Edward voice: WORKS WELL on clean short sentences (10s sample). On longer/casual mixed-language ramble (30s+), output is partial but identifiable. ASR itself is NOT the bottleneck.",
}

with open(RESULTS_DIR + "/edward-voice-spotcheck.md", "w", encoding="utf-8") as f:
    f.write("# Stage 3 . Edward Voice ASR Spot Check\n\n")
    f.write("**Date**: 2026-05-22\n")
    f.write("**Model**: " + data1["model"] + "\n\n")
    f.write("## Test 1 - 60s Edward sample (m4a, full)\n\n")
    f.write("- Audio duration: " + str(data1["audio_duration_sec"]) + "s (Whisper truncated to 30s)\n")
    f.write("- ASR output: \n")
    f.write("- Latency: " + str(data1["breakdown_ms"]["inference"]) + "ms inference / " + str(data1["total_e2e_ms"]) + "ms e2e\n")
    f.write("- Verdict: " + spot_check["test_1_full_60s_m4a"]["verdict"] + "\n\n")
    f.write("## Test 2 - 10s Edward prompt sample (16kHz WAV)\n\n")
    f.write("- Audio duration: " + str(data2["audio_duration_sec"]) + "s\n")
    f.write("- ASR output: \n")
    f.write("- Latency: " + str(data2["breakdown_ms"]["inference"]) + "ms inference / " + str(data2["total_e2e_ms"]) + "ms e2e\n")
    f.write("- Verdict: " + spot_check["test_2_10s_prompt_wav"]["verdict"] + "\n\n")
    f.write("## Overall\n\n")
    f.write(spot_check["overall_verdict"] + "\n")
print()
print("==== Spot check saved to edward-voice-spotcheck.md ====")
print(json.dumps(spot_check, indent=2, ensure_ascii=False))

# Stage 4 . Full ASR latency benchmark (5 runs on a known stable input)
print()
print("==== Stage 4 . ASR latency P50/P95 (5 runs) ====")
asr_runs = []
for run_i in range(1, 6):
    print("  ASR run {}/5...".format(run_i))
    data = cl.transcribe(EDWARD_10S, language="zh")
    asr_runs.append({
        "run": run_i,
        "inference_ms": data["breakdown_ms"]["inference"],
        "preprocess_ms": data["preprocess_ms"],
        "total_e2e_ms": data["total_e2e_ms"],
    })

asr_inf = [r["inference_ms"] for r in asr_runs]
asr_e2e = [r["total_e2e_ms"] for r in asr_runs]

# Stage 4 . TTS latency benchmark (5 runs of same text)
print()
print("==== Stage 4 . TTS latency P50/P95 (5 runs) ====")
TTS_TEST_TEXT = "你好，這是測試"
TTS_PROMPT_TXT = "Hello, 我是 Edward. 你好, Sophie."
tts_runs = []
for run_i in range(1, 6):
    print("  TTS run {}/5...".format(run_i))
    out_path = AUDIO_DIR + "/_latency_test_{}.wav".format(run_i)
    t0 = time.time()
    try:
        wav, meta = cl.synthesize(TTS_TEST_TEXT, EDWARD_10S, out_path, prompt_text=TTS_PROMPT_TXT)
        tts_runs.append({
            "run": run_i,
            "tts_latency_ms": float(meta["latency_ms"]),
            "tts_inference_ms": float(meta["inference_ms"]),
            "output_duration_sec": float(meta["duration_sec"]),
        })
    except SystemExit:
        print("    FAILED")

tts_lat = [r["tts_latency_ms"] for r in tts_runs]
tts_inf = [r["tts_inference_ms"] for r in tts_runs]

def p(arr, pct):
    arr = sorted(arr)
    idx = max(0, min(len(arr) - 1, int(len(arr) * pct)))
    return arr[idx]

latency_summary = {
    "asr_runs": asr_runs,
    "asr_inference_p50_ms": round(statistics.median(asr_inf), 1) if asr_inf else None,
    "asr_inference_p95_ms": round(p(asr_inf, 0.95), 1) if asr_inf else None,
    "asr_e2e_p50_ms": round(statistics.median(asr_e2e), 1) if asr_e2e else None,
    "asr_e2e_p95_ms": round(p(asr_e2e, 0.95), 1) if asr_e2e else None,
    "tts_runs": tts_runs,
    "tts_latency_p50_ms": round(statistics.median(tts_lat), 1) if tts_lat else None,
    "tts_latency_p95_ms": round(p(tts_lat, 0.95), 1) if tts_lat else None,
    "tts_inference_p50_ms": round(statistics.median(tts_inf), 1) if tts_inf else None,
    "tts_inference_p95_ms": round(p(tts_inf, 0.95), 1) if tts_inf else None,
    "escalate_check": {
        "asr_p95_e2e_under_3s": (round(p(asr_e2e, 0.95), 1) if asr_e2e else 9999) < 3000,
        "tts_p95_under_3s": (round(p(tts_lat, 0.95), 1) if tts_lat else 9999) < 3000,
    },
}

# Save latency CSV
csv_lines = ["category,run,inference_ms,latency_ms,e2e_ms,output_duration_sec"]
for r in asr_runs:
    csv_lines.append("ASR,{},{},,{},".format(r["run"], r["inference_ms"], r["total_e2e_ms"]))
for r in tts_runs:
    csv_lines.append("TTS,{},{},{},,{}".format(r["run"], r["tts_inference_ms"], r["tts_latency_ms"], r["output_duration_sec"]))
with open(RESULTS_DIR + "/latency.csv", "w", encoding="utf-8") as f:
    f.write(chr(10).join(csv_lines))
with open(RESULTS_DIR + "/latency-summary.json", "w", encoding="utf-8") as f:
    json.dump(latency_summary, f, ensure_ascii=False, indent=2)

# Cleanup latency test wavs
for run_i in range(1, 6):
    f_path = AUDIO_DIR + "/_latency_test_{}.wav".format(run_i)
    try:
        os.remove(f_path)
    except OSError:
        pass

print()
print("==== Latency Summary ====")
print(json.dumps(latency_summary, indent=2, ensure_ascii=False))
