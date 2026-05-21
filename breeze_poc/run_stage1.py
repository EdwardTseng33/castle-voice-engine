# Stage 1 + 2 + 4 combined runner
import os, sys, json, time, pathlib
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
PROMPT = AUDIO_DIR + "/edward_prompt_10s.wav"
PROMPT_TXT = "Hello, 我是 Edward. 你好, Sophie."

results = []

print("==== Stage 1 . BreezyVoice TTS gen 10 sentences ====")
for i, ref in enumerate(REFS, 1):
    out = AUDIO_DIR + "/t{:02d}.wav".format(i)
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  t{:02d} already exists, skip TTS".format(i))
        continue
    print("  t{:02d}: gen TTS for: {}".format(i, ref[:30]))
    t0 = time.time()
    try:
        wav, meta = cl.synthesize(ref, PROMPT, out, prompt_text=PROMPT_TXT)
        elapsed = time.time() - t0
        results.append({"i": i, "ref": ref, "out": out, "tts_meta": meta, "client_elapsed_ms": round(elapsed*1000, 1), "tts_ok": True})
        print("    OK in {:.1f}s, file {} bytes".format(elapsed, len(wav)))
    except SystemExit as e:
        print("    FAILED")
        results.append({"i": i, "ref": ref, "tts_ok": False})

# Save partial progress
with open(AUDIO_DIR + "/../results/stage1_progress.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print()
print("==== Stage 1 done ====")
print("OK:", sum(1 for r in results if r.get("tts_ok")))
print("FAIL:", sum(1 for r in results if not r.get("tts_ok")))
