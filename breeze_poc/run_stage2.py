# Stage 2 + 4 . Round-trip ASR + CER + Latency
import os, sys, json, time, pathlib, statistics
sys.path.insert(0, "C:/Users/Administrator/Claude/castle-voice-engine/breeze_poc")
import client as cl

REFS = [
    "我今天早上跑了五公里、覺得體力比上個月好很多",
    "蘇菲幫我看一下 BeyondPath 昨天的留存率有沒有跌",
    "卡西法去確認 Vercel preview URL 跑得起來",
    "派蕪菁頭看用戶 cohort 的退訂原因 top 3",
    "我預算大概一個月五千塊、能不能撐三個月",
    "三點半開會、會議室在 12 樓 A 區",
    "這個 component refactor 一下、別讓 props drilling 變五層",
    "CFO 拉預算的時候、記得 highlight 那個 ROI 是 3.2 倍",
    "我有點不耐煩了、能不能直接給我結論不要鋪陳",
    "Sophie can you help me draft an email to Marc about Q3 strategy",
]

AUDIO_DIR = "C:/Users/Administrator/Claude/castle-voice-engine/breeze_poc/phase1-poc/audio"
RESULTS_DIR = "C:/Users/Administrator/Claude/castle-voice-engine/breeze_poc/phase1-poc/results"

# jiwer for CER
try:
    import jiwer
    HAVE_JIWER = True
except ImportError:
    HAVE_JIWER = False
    print("NOTE: jiwer not installed locally - will compute simple char accuracy")

def simple_cer(ref, hyp):
    """fallback CER: counts character substitutions"""
    import difflib
    matcher = difflib.SequenceMatcher(None, ref, hyp)
    n = len(ref)
    if n == 0:
        return 0.0
    edit_dist = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            edit_dist += i2 - i1
        elif tag == "insert":
            edit_dist += j2 - j1
    return edit_dist / n

# Stage 2 + 4 . Transcribe + Latency
print("==== Stage 2 + 4 . ASR round-trip + CER + Latency ====")
asr_results = []
asr_latencies = []
for i, ref in enumerate(REFS, 1):
    wav_path = AUDIO_DIR + "/t{:02d}.wav".format(i)
    if not os.path.exists(wav_path):
        print("  t{:02d}: skip - WAV missing".format(i))
        continue
    print("  t{:02d}: ASR {}".format(i, ref[:30]))
    t0 = time.time()
    try:
        data = cl.transcribe(wav_path, language="zh")
        elapsed_ms = (time.time() - t0) * 1000
        hyp = data["text"]
        # Use jiwer if available else simple
        if HAVE_JIWER:
            cer = jiwer.cer(ref, hyp)
        else:
            cer = simple_cer(ref, hyp)
        result = {
            "i": i,
            "ref": ref,
            "hyp": hyp,
            "cer_pct": round(cer * 100, 2),
            "ref_len": len(ref),
            "hyp_len": len(hyp),
            "asr_inference_ms": data["breakdown_ms"]["inference"],
            "asr_total_e2e_ms": data["total_e2e_ms"],
            "client_roundtrip_ms": round(elapsed_ms, 1),
            "audio_duration_sec": data["audio_duration_sec"],
        }
        asr_results.append(result)
        asr_latencies.append(data["breakdown_ms"]["inference"])
        print("    CER: {}% | hyp: {}".format(result["cer_pct"], hyp[:50]))
    except SystemExit:
        print("    FAILED")

# Compute aggregates
if asr_results:
    cers = [r["cer_pct"] for r in asr_results]
    inference_ms = [r["asr_inference_ms"] for r in asr_results]
    e2e_ms = [r["asr_total_e2e_ms"] for r in asr_results]
    
    summary = {
        "asr_model": "MediaTek-Research/Breeze-ASR-25",
        "n_samples": len(asr_results),
        "cer_pct_mean": round(statistics.mean(cers), 2),
        "cer_pct_median": round(statistics.median(cers), 2),
        "cer_pct_max": round(max(cers), 2),
        "cer_pct_min": round(min(cers), 2),
        "asr_inference_p50_ms": round(statistics.median(inference_ms), 1),
        "asr_inference_p95_ms": round(sorted(inference_ms)[int(len(inference_ms)*0.95)] if len(inference_ms) > 1 else inference_ms[0], 1),
        "asr_e2e_p50_ms": round(statistics.median(e2e_ms), 1),
        "asr_e2e_p95_ms": round(sorted(e2e_ms)[int(len(e2e_ms)*0.95)] if len(e2e_ms) > 1 else e2e_ms[0], 1),
        "baseline_vendor_cer_pct": 7.97,
        "verdict_vs_baseline": "OK (below baseline)" if statistics.mean(cers) <= 7.97 else "MARGINAL" if statistics.mean(cers) <= 15 else "ESCALATE",
    }

# Write CSV
csv_lines = ["i,ref,hyp,cer_pct,ref_len,hyp_len,audio_duration_sec,asr_inference_ms,asr_total_e2e_ms,client_roundtrip_ms"]
for r in asr_results:
    # escape commas/quotes in text
    def esc(s):
        return chr(34) + str(s).replace(chr(34), chr(34)*2) + chr(34)
    csv_lines.append(",".join([
        str(r["i"]), esc(r["ref"]), esc(r["hyp"]),
        str(r["cer_pct"]), str(r["ref_len"]), str(r["hyp_len"]),
        str(r["audio_duration_sec"]), str(r["asr_inference_ms"]), str(r["asr_total_e2e_ms"]),
        str(r["client_roundtrip_ms"]),
    ]))
with open(RESULTS_DIR + "/round-trip-cer.csv", "w", encoding="utf-8") as f:
    f.write(chr(10).join(csv_lines))
print()
print("==== Summary ====")
print(json.dumps(summary, indent=2, ensure_ascii=False))

with open(RESULTS_DIR + "/round-trip-cer-summary.json", "w", encoding="utf-8") as f:
    json.dump({"summary": summary, "per_sample": asr_results}, f, ensure_ascii=False, indent=2)
