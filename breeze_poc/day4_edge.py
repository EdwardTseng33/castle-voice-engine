import asyncio, io, json, time, pathlib, statistics, uuid
import urllib.request, urllib.error
import edge_tts

ROOT = pathlib.Path("C:/Users/Administrator/Claude/castle-voice-engine")
POC = ROOT / "breeze_poc" / "phase1-poc"
AUDIO = POC / "audio"
RESULTS = POC / "results"
SENT = POC / "sentences.txt"
EDGE_VOICE = "zh-TW-HsiaoChenNeural"
EP = "https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run"

TOKEN = None
with open(ROOT / ".env", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line.startswith("BREEZE_AUTH_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip().strip(chr(34)).strip(chr(39))
            break

sentences = []
with open(SENT, "r", encoding="utf-8") as f:
    for line in f:
        line = line.rstrip()
        if line and not line.startswith("#"):
            sentences.append(line)
print("Loaded", len(sentences), "sentences")

DQ = chr(34)
SQ = chr(39)

def mp(fields, files):
    b = "----CastleDay4" + uuid.uuid4().hex
    body = io.BytesIO()
    CRLF = b"\r\n"
    for k, v in fields.items():
        body.write(("--" + b).encode()); body.write(CRLF)
        body.write(("Content-Disposition: form-data; name=" + DQ + k + DQ).encode()); body.write(CRLF); body.write(CRLF)
        body.write(v.encode()); body.write(CRLF)
    for fname, filename, c in files:
        body.write(("--" + b).encode()); body.write(CRLF)
        body.write(("Content-Disposition: form-data; name=" + DQ + fname + DQ + "; filename=" + DQ + filename + DQ).encode()); body.write(CRLF)
        body.write(b"Content-Type: application/octet-stream"); body.write(CRLF); body.write(CRLF)
        body.write(c); body.write(CRLF)
    body.write(("--" + b + "--").encode()); body.write(CRLF)
    return body.getvalue(), b

def call_asr(wav, lang="zh"):
    body, boundary = mp({"language": lang}, [("file", "in.wav", wav)])
    req = urllib.request.Request(EP + "/breeze/asr/transcribe", data=body,
        headers={"X-Breeze-Token": TOKEN, "Content-Type": "multipart/form-data; boundary=" + boundary, "Content-Length": str(len(body))}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            d = json.loads(resp.read()); d["client_total_ms"] = round((time.time() - t0) * 1000, 1); return d
    except urllib.error.HTTPError as e:
        return {"error": "HTTP " + str(e.code) + ": " + e.read().decode("utf-8", errors="replace")[:300], "client_total_ms": (time.time() - t0) * 1000}

def cer(ref, hyp):
    ref = ref.strip(); hyp = hyp.strip()
    n, m = len(ref), len(hyp)
    if n == 0: return 1.0 if m > 0 else 0.0
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[0]; dp[0] = i
        for j in range(1, m + 1):
            cur = dp[j]
            if ref[i - 1] == hyp[j - 1]: dp[j] = prev
            else: dp[j] = 1 + min(prev, dp[j - 1], dp[j])
            prev = cur
    return dp[m] / n

async def synth(text):
    t0 = time.time()
    c = edge_tts.Communicate(text, EDGE_VOICE)
    buf = io.BytesIO()
    async for chunk in c.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue(), (time.time() - t0) * 1000

async def main():
    s1 = []
    print("=== STAGE 1: Edge TTS synth ===")
    for i, text in enumerate(sentences, start=1):
        tag = "t" + (("0" + str(i)) if i < 10 else str(i))
        out = AUDIO / (tag + "-edge.wav")
        try:
            ab, lat = await synth(text)
            with open(out, "wb") as f: f.write(ab)
            s1.append({"tag": tag, "text": text, "path": str(out), "bytes": len(ab), "lat_ms": round(lat, 1)})
            print("[S1]", tag, "OK", len(ab), "B lat=", round(lat, 1), "ms")
        except Exception as e:
            print("[S1]", tag, "FAIL", str(e)[:200])
            s1.append({"tag": tag, "text": text, "error": str(e)[:200]})
    s1_ok = [s for s in s1 if "error" not in s]
    print("Stage1:", len(s1_ok), "/", len(s1))

    print("=== STAGE 2: ASR round-trip ===")
    csv_rows = ["tag,ref_chars,hyp_chars,cer_pct,client_total_ms,server_e2e_ms,inference_ms,asr_text,ref_text"]
    cers = []; asr_lats = []
    for s in s1:
        if "error" in s:
            csv_rows.append(",".join([s["tag"], "", "", "", "", "", "", "ERROR", s["text"].replace(",", " ")]))
            continue
        with open(s["path"], "rb") as f: wav = f.read()
        r = call_asr(wav)
        if "error" in r:
            csv_rows.append(",".join([s["tag"], "", "", "", str(r.get("client_total_ms", "")), "", "", "ASR_ERROR", s["text"].replace(",", " ")]))
            print("[S2]", s["tag"], "ASR FAIL", r["error"][:200])
            continue
        ref = s["text"]; hyp = r.get("text", "")
        c = cer(ref, hyp); cp = round(c * 100, 2); cers.append(cp)
        e2e = float(r.get("total_e2e_ms", r.get("client_total_ms", 0))); inf = float(r.get("inference_ms", 0))
        asr_lats.append(e2e)
        csv_rows.append(",".join([
            s["tag"], str(len(ref)), str(len(hyp)), str(cp),
            str(r["client_total_ms"]), str(round(e2e, 1)), str(round(inf, 1)),
            DQ + hyp.replace(DQ, SQ) + DQ,
            DQ + ref.replace(DQ, SQ) + DQ,
        ]))
        print("[S2]", s["tag"], "CER=", cp, "% ref=", len(ref), "hyp=", len(hyp), "inf=", round(inf, 1), "ms")
    with open(RESULTS / "edge-round-trip-cer.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(csv_rows) + "\n")

    tts_lats = [s["lat_ms"] for s in s1_ok]
    def pct(vs, p):
        if not vs: return 0
        sv = sorted(vs); k = (len(sv) - 1) * p / 100; fi = int(k); ci = min(fi + 1, len(sv) - 1)
        return sv[fi] if fi == ci else sv[fi] + (sv[ci] - sv[fi]) * (k - fi)

    lat = ["category,count,p50_ms,p95_ms,min_ms,max_ms,mean_ms"]
    for cat, lats in [("edge_tts_client_latency", tts_lats), ("breeze_asr_server_e2e", asr_lats)]:
        if lats:
            lat.append(",".join([cat, str(len(lats)), str(round(pct(lats, 50), 1)), str(round(pct(lats, 95), 1)),
                                  str(round(min(lats), 1)), str(round(max(lats), 1)), str(round(statistics.mean(lats), 1))]))
    with open(RESULTS / "edge-latency.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(lat) + "\n")

    summary = {
        "_meta": {"owner": "calcifer", "ship_date": "2026-05-22", "stage": "Day 4",
                  "voice_provider": "Microsoft Edge TTS (free, local, no API key)",
                  "voice": EDGE_VOICE,
                  "asr_provider": "MediaTek-Research/Breeze-ASR-25 (Modal A10G)"},
        "stage_1_tts": {"ok": len(s1_ok), "total": len(s1),
            "p50_ms": round(pct(tts_lats, 50), 1) if tts_lats else None,
            "p95_ms": round(pct(tts_lats, 95), 1) if tts_lats else None,
            "mean_ms": round(statistics.mean(tts_lats), 1) if tts_lats else None},
        "stage_2_cer": {"count": len(cers),
            "cer_mean_pct": round(statistics.mean(cers), 2) if cers else None,
            "cer_median_pct": round(statistics.median(cers), 2) if cers else None,
            "cer_min_pct": round(min(cers), 2) if cers else None,
            "cer_max_pct": round(max(cers), 2) if cers else None},
        "baseline_breezyvoice_day3": {"cer_mean_pct": 85.86, "cer_median_pct": 95.0, "tts_p50_ms": 7349.0, "tts_p95_ms": 9860.0},
        "monthly_cost": {
            "edge_tts": "$0/month (Microsoft free)",
            "breezyvoice_modal": "~$30-50/month dev (A10G GPU on-demand)",
            "breeze_asr_modal": "~$10-20/month dev (T4 GPU on-demand)"},
        "go_no_go": {}}
    cm = summary["stage_2_cer"]["cer_mean_pct"]; p95 = summary["stage_1_tts"]["p95_ms"]
    if cm is not None: summary["go_no_go"]["edge_tts_cer_vs_5pct"] = "PASS" if cm < 5 else ("MARGINAL" if cm < 15 else "FAIL")
    if p95 is not None: summary["go_no_go"]["edge_tts_p95_vs_3000ms"] = "PASS" if p95 < 3000 else "FAIL"
    if cm and p95:
        bz_cer = summary["baseline_breezyvoice_day3"]["cer_mean_pct"]; bz_p95 = summary["baseline_breezyvoice_day3"]["tts_p95_ms"]
        wins = (cm < bz_cer) and (p95 < bz_p95)
        summary["go_no_go"]["verdict_vs_breezyvoice"] = "Edge TTS WINS on both axes (lower CER, lower P95)" if wins else "INCONCLUSIVE - review per-axis"
    with open(RESULTS / "edge-comparison-data.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("=== DONE ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

asyncio.run(main())
