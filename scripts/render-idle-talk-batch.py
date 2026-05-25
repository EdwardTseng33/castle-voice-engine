"""
Phase 8 (2026-05-25 calcifer · Edward 嘴微動 OK 拍板 · Phase A):
Offline batch render 4 idle reference -> 4 mp4 with mouth movement.

Pipeline:
  1) Convert source mp3 -> 16kHz mono PCM wav locally (imageio_ffmpeg binary)
  2) Read wav bytes
  3) For each ref_id in [idle, idle-2, idle-3, idle-4]:
       call MuseTalkRunner.generate_lipsync_mp4.remote(ref_id, audio_bytes, fps=25)
       write returned video_bytes to outputs/sophie-<ref>-talk.mp4
  4) Print summary: file size, frame count, duration_s, elapsed

Usage:
  python scripts/render-idle-talk-batch.py

Hard rules (Edward Phase A scope):
  - No prod app change (generate_lipsync_mp4 is additive)
  - No deploy to staging/prod
  - Outputs to outputs/ (not castle/static/ - won't overwrite existing idle.mp4)
  - Budget < NT$10 (~5min A10G)
"""

import io
import os
import sys
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_SRC = REPO_ROOT / "breeze_poc/phase1-poc/results/tts-natural-ab/sophie-voice-prompts/edge-xiaoyu-sophie-prompt.mp3"
OUTPUT_DIR = REPO_ROOT / "outputs"

REF_IDS = ["idle", "idle-2", "idle-3", "idle-4"]
OUTPUT_NAME_MAP = {
    "idle": "sophie-idle-talk.mp4",
    "idle-2": "sophie-idle-2-talk.mp4",
    "idle-3": "sophie-idle-3-talk.mp4",
    "idle-4": "sophie-idle-4-talk.mp4",
}


def convert_to_16k_mono_pcm_wav(mp3_path: Path, wav_path: Path) -> None:
    """Use imageio_ffmpeg bundled ffmpeg to transcode mp3 -> 16k mono PCM-16 wav."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y", "-v", "warning",
        "-i", str(mp3_path),
        "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le",
        str(wav_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"FFmpeg stderr: {r.stderr[-500:]}", file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed rc={r.returncode}")


def main():
    if not AUDIO_SRC.exists():
        print(f"FAIL audio not found: {AUDIO_SRC}", file=sys.stderr)
        sys.exit(1)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Convert mp3 -> wav locally
    wav_path = OUTPUT_DIR / "_edge-xiaoyu-16k-mono.wav"
    print(f"[1/3] mp3 -> 16k mono PCM wav: {wav_path}")
    convert_to_16k_mono_pcm_wav(AUDIO_SRC, wav_path)
    audio_bytes = wav_path.read_bytes()
    print(f"      wav: {len(audio_bytes)/1024:.1f} KB")

    # 2) Connect to deployed Modal app
    print(f"[2/3] connect Modal: castle-voice-engine-musetalk-poc")
    import modal
    MuseTalkRunner = modal.Cls.from_name("castle-voice-engine-musetalk-poc", "MuseTalkRunner")
    runner = MuseTalkRunner()

    # Sanity: list_references first to confirm 4 idle refs loaded
    refs = runner.list_references.remote()
    print(f"      refs available: {refs}")
    missing = [r for r in REF_IDS if r not in refs]
    if missing:
        print(f"FAIL missing refs: {missing}", file=sys.stderr)
        print(f"     available: {list(refs.keys())}", file=sys.stderr)
        sys.exit(2)

    # 3) Render 4 mp4
    print(f"[3/3] render 4 lipsync mp4 (sequential, ref_id varies)")
    results = []
    t_total_start = time.time()
    for ref_id in REF_IDS:
        out_path = OUTPUT_DIR / OUTPUT_NAME_MAP[ref_id]
        t0 = time.time()
        print(f"  -> generating ref={ref_id} ...", flush=True)
        result = runner.generate_lipsync_mp4.remote(ref_id, audio_bytes, fps=25)
        elapsed = time.time() - t0
        if "error" in result and result["error"]:
            print(f"     FAIL ref={ref_id}: {result['error']}")
            results.append({"ref_id": ref_id, "ok": False, "error": result["error"]})
            continue
        video_bytes = result.get("video_bytes", b"")
        if not video_bytes:
            print(f"     FAIL ref={ref_id}: empty video_bytes")
            results.append({"ref_id": ref_id, "ok": False, "error": "empty video_bytes"})
            continue
        out_path.write_bytes(video_bytes)
        size_mb = len(video_bytes) / 1024 / 1024
        results.append({
            "ref_id": ref_id,
            "ok": True,
            "path": str(out_path),
            "size_mb": size_mb,
            "frame_count": result.get("frame_count", 0),
            "fps": result.get("fps", 25),
            "duration_s": result.get("duration_s", 0),
            "render_s": elapsed,
        })
        print(f"     OK ref={ref_id} {size_mb:.2f}MB frames={result.get('frame_count')} duration={result.get('duration_s'):.2f}s render={elapsed:.1f}s")
    t_total = time.time() - t_total_start

    # Summary
    print("\n=== SUMMARY ===")
    ok_count = sum(1 for r in results if r["ok"])
    print(f"OK {ok_count}/4 · total render {t_total:.1f}s · GPU est ${t_total*1.10/3600:.4f} (~NT${t_total*1.10/3600*32:.2f})")
    for r in results:
        if r["ok"]:
            print(f"  {r['ref_id']:>8s}  {r['size_mb']:>5.2f}MB  {r['frame_count']:>4d}frames  {r['duration_s']:.2f}s  -> {Path(r['path']).name}")
        else:
            print(f"  {r['ref_id']:>8s}  FAIL: {r.get('error')}")

    if ok_count < 4:
        sys.exit(3)


if __name__ == "__main__":
    main()
