# breeze_poc/run_chatterbox_longform_mtl.py
# Voice Path v2.0 Phase 1 PoC - Chatterbox-MTL LONGFORM CORRECTION RUN
# 2026-05-22 calcifer - L01 (383 chars work report) / L02 (196 chars emotional) / L03 (208 chars cn-en mixed)
# CORRECTION: 5/22 upper longform run used base English-only model · zh text rendered with English accent
# This re-run switches to ChatterboxMultilingualTTS + language_id='zh' · overwrites L01-L03.wav + metadata.json
# Test: voice consistency / volume stability / pause naturalness / cn-en code-switching / language correctness
import json, pathlib, time
ROOT = pathlib.Path("C:/Users/Administrator/Claude/castle-voice-engine")
RESULTS = ROOT / "breeze_poc" / "phase1-poc" / "results" / "tts-natural-ab"
PROMPT_PATH = RESULTS / "sophie-voice-prompts" / "edge-xiaoyu-sophie-prompt.mp3"
OUT_DIR = RESULTS / "chatterbox-turbo-longform"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TESTS = [
    {
        "id": "L01",
        "scenario": "work_report",
        "char_count_target": 350,
        "text": "Edward、跟你報告今天城堡的進度。沙利曼那邊已經把 Taiwan-Tongues 跟 VibeVoice 兩家的隱私審查跑完了、verdict 給的是 Tier B 條件式可用、Phase 2 PoC 階段沒問題、Phase 4 對外商用前要找律師再審一次。霍爾的 v3 計畫書也 ship 了、補上雙模型路由跟家庭多語對話兩段、字數壓在兩千五百以下。卡西法那邊正在跑 Chatterbox-Turbo 第二輪長文測試、會跟前面四家 voice profile 對比、預計兩小時內你就能聽到完整結果。我這邊已經把 5 月 22 號這場 sprint 的所有決策都寫進 ADR-018 跟 ADR-019、紀律檔也補了「中國公司開源 model 本機跑分 Tier」這條 cross-product 規矩、未來城堡所有產品都能繼承。今天就這些、你想討論哪個再叫我。",
    },
    {
        "id": "L02",
        "scenario": "emotional",
        "char_count_target": 230,
        "text": "今天真的有點累、從清晨開始追進度、技術選型來回好幾輪、聲音工具盲測踩了好幾個坑、normalize 跟 inference 入口配置都修了。但收穫也明顯、找到聯發科 Taigi 系列、發現沙利曼的 cross-product Tier 矩陣需要升級、Chatterbox-Turbo 真的可能比 Edge TTS 更自然。明天我們再決定 Phase 2 主路怎麼走、今天先把這些先存著、別急。",
    },
    {
        "id": "L03",
        "scenario": "cn_en_mixed_engineering",
        "char_count_target": 200,
        "text": "你那個 BeyondPath 的 dashboard 我看過、retention 數據看起來沒問題、但 conversion funnel 那邊的 stage 3 drop 比較明顯、可能要派蕪菁頭去看 user behavior。另外 PR 那條我已經跑過 lint 沒問題、merge 之前再跑一次 e2e test 就可以 ship 到 main。BeyondPath 2.0 的 spec 你想什麼時候開始？",
    },
]

with open(PROMPT_PATH, "rb") as f:
    prompt_bytes = f.read()
print("Loaded voice prompt:", PROMPT_PATH.name, "(", len(prompt_bytes), "bytes )")

import modal
# Use MTL app (separate from base chatterbox-poc · MTL = multilingual zh-capable)
ChatterboxMultilingual = modal.Cls.from_name("chatterbox-mtl-poc", "ChatterboxMultilingual")
cls = ChatterboxMultilingual()

meta = {
    "test_name": "Chatterbox-MTL Longform Stability Test (CORRECTION RUN)",
    "purpose": "Verify voice consistency / volume stability / pause naturalness / cn-en code-switching on 200-400 char passages · MTL zh-correct",
    "model": "Resemble AI Chatterbox-Multilingual",
    "model_version": "ResembleAI/chatterbox (chatterbox-tts==0.1.7)",
    "model_class": "ChatterboxMultilingualTTS",
    "language_id": "zh",
    "model_size": "0.5B Llama backbone · MTL variant · 23 languages incl Chinese",
    "deployment": "Modal A10G GPU, chatterbox-mtl-poc app (separate from base chatterbox-poc), edwardt0303 namespace",
    "voice_ref_source": "Azure Edge TTS zh-TW-HsiaoYuNeural (Xiao Yu, same as previous MTL short-test)",
    "voice_ref_file": "../sophie-voice-prompts/edge-xiaoyu-sophie-prompt.mp3",
    "voice_ref_duration_sec": 30,
    "voice_clone": "zero-shot from prompt mp3 (native Chatterbox API)",
    "normalize_target": "-1 dBFS peak (0.9 of int16 max, built into Modal endpoint)",
    "endpoint": "Modal class direct call (synthesize_with_voice)",
    "license": "MIT (model) + Apache-2.0 (wrapper) + Azure TTS terms for voice ref",
    "ship_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
    "ship_session": "calcifer 5/22 Chatterbox CORRECTION longform run · MTL model · zh language_id",
    "correction_note": "5/22 upper L01-L03 used base (English-only) ChatterboxTTS · zh chars rendered with English accent · Edward caught bug · this re-run uses ChatterboxMultilingualTTS + language_id=\"zh\" · overwrote L01-L03.wav + metadata.json in chatterbox-turbo-longform/",
    "industry_blind_test_claim": "63.75% prefer over ElevenLabs (per Resemble AI · base model claim, MTL likely similar but not independently verified)",
    "test_scenarios": [
        {"id": "L01", "scenario": "work_report", "target_chars": 350, "evaluates": "long-form voice drift over ~25s audio"},
        {"id": "L02", "scenario": "emotional", "target_chars": 230, "evaluates": "emotional tone consistency"},
        {"id": "L03", "scenario": "cn_en_mixed_engineering", "target_chars": 200, "evaluates": "code-switching English tech terms"},
    ],
    "evaluation_criteria_for_edward": {
        "voice_consistency": "Does the voice stay the same person from start to end?",
        "volume_stability": "Any sentence noticeably louder or quieter than rest?",
        "pause_naturalness": "Are comma / period pauses natural?",
        "cn_en_mixing": "Do English tech terms pronounce correctly?",
        "language_correctness": "Mandarin should sound native (NOT English-accented · fixes 5/22 upper bug)",
    },
    "samples": [],
}

latencies = []
inference_times = []
for test in TESTS:
    tid = test["id"]
    text = test["text"]
    actual_chars = len(text)
    out_wav = OUT_DIR / (tid + ".wav")
    print("\n[" + tid + "] scenario=" + test["scenario"] + " chars=" + str(actual_chars) + " (target=" + str(test["char_count_target"]) + ")")
    print("  text preview:", text[:60], "...")
    t0 = time.time()
    try:
        result = cls.synthesize_with_voice.remote(
            text=text,
            voice_prompt_bytes=prompt_bytes,
            voice_format="mp3",
            language_id="zh",
        )
        client_total_ms = round((time.time() - t0) * 1000, 1)
        wav_bytes = result["wav_bytes"]
        with open(out_wav, "wb") as fh:
            fh.write(wav_bytes)
        latencies.append(result["latency_ms"])
        inference_times.append(result["inference_ms"])
        expected_min_dur = actual_chars / 6.0
        actual_dur = result["duration_sec"]
        truncation_warning = actual_dur < expected_min_dur * 0.7
        sample_entry = {
            "id": tid,
            "scenario": test["scenario"],
            "char_count": actual_chars,
            "char_count_target": test["char_count_target"],
            "text": text,
            "file": out_wav.name,
            "latency_ms": result["latency_ms"],
            "inference_ms": result["inference_ms"],
            "client_total_ms": client_total_ms,
            "duration_sec": result["duration_sec"],
            "sample_rate": result["sample_rate"],
            "language_id": result.get("language_id", "zh"),
            "model_class": result.get("model_class", "ChatterboxMultilingualTTS"),
            "voice_ref": result["voice_ref"],
            "voice_clone_enabled": result["voice_clone_enabled"],
            "voice_prompt_duration_sec": result["voice_prompt_duration_sec"],
            "expected_min_duration_sec_loose": round(expected_min_dur, 1),
            "truncation_warning": truncation_warning,
            "chars_per_sec_audio": round(actual_chars / actual_dur, 2) if actual_dur > 0 else None,
        }
        meta["samples"].append(sample_entry)
        warn = " [TRUNCATION WARNING]" if truncation_warning else ""
        print("  OK lat=" + str(result["latency_ms"]) + "ms inf=" + str(result["inference_ms"]) + "ms dur=" + str(actual_dur) + "s lang=" + str(result.get("language_id", "zh")) + warn)
        print("  ->", out_wav.name, "(", len(wav_bytes), "bytes )")
    except Exception as e:
        client_total_ms = round((time.time() - t0) * 1000, 1)
        err = str(e)[:500]
        print("  FAIL after", client_total_ms, "ms:", err)
        meta["samples"].append({
            "id": tid,
            "scenario": test["scenario"],
            "char_count": actual_chars,
            "text": text,
            "error": err,
            "client_total_ms": client_total_ms,
        })

if latencies:
    latencies.sort()
    n = len(latencies)
    meta["latency_p50_ms"] = round(latencies[n // 2], 1)
    meta["latency_max_ms"] = round(max(latencies), 1)
    meta["latency_mean_ms"] = round(sum(latencies) / n, 1)
    meta["success_count"] = len(latencies)
else:
    meta["success_count"] = 0
if inference_times:
    inference_times.sort()
    n = len(inference_times)
    meta["inference_p50_ms"] = round(inference_times[n // 2], 1)
    meta["inference_max_ms"] = round(max(inference_times), 1)
    meta["inference_mean_ms"] = round(sum(inference_times) / n, 1)

with open(OUT_DIR / "metadata.json", "w", encoding="utf-8") as fh:
    json.dump(meta, fh, indent=2, ensure_ascii=False)
print("\nDone.", meta["success_count"], "/", len(TESTS), "ok. P50=", meta.get("latency_p50_ms"), "ms Max=", meta.get("latency_max_ms"), "ms")
print("Output dir:", OUT_DIR)
print("Metadata:", OUT_DIR / "metadata.json")
