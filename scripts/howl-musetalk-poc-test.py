"""
PoC test for Howl's MuseTalk acceptance spec (2026-05-26 calcifer · Edward 重派).

Hard rules (Edward 紅線):
  - PoC test only · NO prod / v0.7 main path touched
  - Single ref (`idle`) · NO 4-ref batch
  - Truncate audio to first 8 seconds (Howl spec: 5-8s)
  - Output to outputs/sophie-musetalk-howl-test.mp4
  - Budget < NT$10

Pipeline:
  1) mp3 -> 16k mono PCM wav (local imageio_ffmpeg) -> truncate to 8s
  2) Modal.Cls.from_name("castle-voice-engine-musetalk-poc", "MuseTalkRunner")
  3) runner.list_references.remote() sanity check `idle` exists
  4) runner.generate_lipsync_mp4.remote("idle", audio_bytes, fps=25)
  5) Write mp4 + report timings + ffprobe codec
"""

import os
import sys
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_SRC = REPO_ROOT / "breeze_poc/phase1-poc/results/tts-natural-ab/sophie-voice-prompts/edge-xiaoyu-sophie-prompt.mp3"
OUTPUT_DIR = REPO_ROOT / "outputs"
OUTPUT_NAME = "sophie-musetalk-howl-test.mp4"
TRUNCATE_SECONDS = 8


def convert_to_16k_mono_pcm_wav(mp3_path: Path, wav_path: Path, max_seconds: int) -> None:
    """imageio_ffmpeg: mp3 -> truncate -> 16k mono PCM-16 wav."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y", "-v", "warning",
        "-i", str(mp3_path),
        "-t", str(max_seconds),
        "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le",
        str(wav_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"FFmpeg stderr: {r.stderr[-500:]}", file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed rc={r.returncode}")


def ffprobe_codec(mp4_path: Path) -> dict:
    """ffprobe 拿 video codec + audio codec + resolution + fps + duration."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    # ffprobe path is alongside ffmpeg
    ffprobe_exe = ffmpeg_exe.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe_exe):
        # Fallback: use ffmpeg -i to parse stderr
        cmd = [ffmpeg_exe, "-i", str(mp4_path)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return {"raw_stderr": r.stderr[-2000:]}
    cmd = [ffprobe_exe, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(mp4_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return {"stdout": r.stdout, "stderr": r.stderr[-500:]}


def main():
    print(f"=== HOWL MUSETALK POC TEST (2026-05-26 calcifer) ===")
    print(f"video ref:  castle/static/sophie-idle.mp4 (via Modal ref_id='idle')")
    print(f"audio src:  {AUDIO_SRC.name}")
    print(f"truncate:   first {TRUNCATE_SECONDS}s")
    print(f"output:     outputs/{OUTPUT_NAME}")
    print()

    if not AUDIO_SRC.exists():
        print(f"FAIL audio not found: {AUDIO_SRC}", file=sys.stderr)
        sys.exit(1)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # [1/5] mp3 -> truncate 8s -> 16k mono PCM wav
    # ============================================================
    wav_path = OUTPUT_DIR / "_howl-poc-test-8s.wav"
    print(f"[1/5] mp3 -> 16k mono PCM wav (truncate {TRUNCATE_SECONDS}s): {wav_path.name}")
    t_step1 = time.time()
    convert_to_16k_mono_pcm_wav(AUDIO_SRC, wav_path, TRUNCATE_SECONDS)
    audio_bytes = wav_path.read_bytes()
    print(f"      wav: {len(audio_bytes)/1024:.1f} KB · {time.time()-t_step1:.2f}s")
    print()

    # ============================================================
    # [2/5] Connect deployed Modal app
    # ============================================================
    print(f"[2/5] connect Modal app: castle-voice-engine-musetalk-poc")
    t_step2 = time.time()
    import modal
    MuseTalkRunner = modal.Cls.from_name("castle-voice-engine-musetalk-poc", "MuseTalkRunner")
    runner = MuseTalkRunner()
    print(f"      connected · {time.time()-t_step2:.2f}s")
    print()

    # ============================================================
    # [3/5] Sanity: list_references; confirm `idle` exists
    # ============================================================
    print(f"[3/5] list_references (warm-up cold start if needed)")
    t_cold_start = time.time()
    refs = runner.list_references.remote()
    cold_start_s = time.time() - t_cold_start
    print(f"      refs available: {list(refs.keys()) if isinstance(refs, dict) else refs}")
    print(f"      list_references roundtrip: {cold_start_s:.2f}s (proxy for cold start)")
    if isinstance(refs, dict):
        if "idle" not in refs:
            print(f"FAIL `idle` ref not enrolled. Available: {list(refs.keys())}", file=sys.stderr)
            sys.exit(2)
    print()

    # ============================================================
    # [4/5] generate_lipsync_mp4
    # ============================================================
    print(f"[4/5] generate_lipsync_mp4(ref='idle', audio={len(audio_bytes)/1024:.1f}KB, fps=25)")
    t_infer = time.time()
    result = runner.generate_lipsync_mp4.remote("idle", audio_bytes, fps=25)
    infer_total_s = time.time() - t_infer
    print(f"      total roundtrip (inference + transfer): {infer_total_s:.2f}s")
    if "error" in result and result["error"]:
        print(f"FAIL: {result['error']}", file=sys.stderr)
        sys.exit(3)
    video_bytes = result.get("video_bytes", b"")
    if not video_bytes:
        print(f"FAIL empty video_bytes", file=sys.stderr)
        sys.exit(4)
    out_path = OUTPUT_DIR / OUTPUT_NAME
    out_path.write_bytes(video_bytes)
    size_mb = len(video_bytes) / 1024 / 1024
    print(f"      wrote: {out_path}")
    print(f"      size: {size_mb:.2f} MB · frames: {result.get('frame_count')} · "
          f"duration_s: {result.get('duration_s'):.2f} · fps: {result.get('fps')}")
    print()

    # ============================================================
    # [5/5] ffprobe codec + report
    # ============================================================
    print(f"[5/5] ffprobe codec verify")
    probe = ffprobe_codec(out_path)
    if "stdout" in probe and probe["stdout"]:
        print(probe["stdout"][:3000])
    else:
        print(probe.get("raw_stderr", "n/a"))
    print()

    # ============================================================
    # SUMMARY
    # ============================================================
    gpu_cost_usd = infer_total_s * 1.10 / 3600  # A10G $1.10/hr
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"output:                outputs/{OUTPUT_NAME}")
    print(f"size:                  {size_mb:.2f} MB")
    print(f"duration:              {result.get('duration_s'):.2f}s")
    print(f"frame_count:           {result.get('frame_count')}")
    print(f"fps:                   {result.get('fps')}")
    print()
    print(f"timing breakdown:")
    print(f"  list_references RTT: {cold_start_s:.2f}s  (proxy: Modal cold start + container ready)")
    print(f"  inference + xfer:    {infer_total_s:.2f}s  (full call: whisper + unet + vae + blend + ffmpeg + transfer)")
    print()
    print(f"cost (A10G):           ~${gpu_cost_usd:.4f} USD  (~NT${gpu_cost_usd*32:.2f})")
    print(f"budget (<NT$10):       {'OK' if gpu_cost_usd*32 < 10 else 'OVER'}")
    print()
    print("Note: granular timings (whisper / unet+vae / blending) printed by Modal logs.")
    print("      Run: python -m modal app logs castle-voice-engine-musetalk-poc | tail -50")


if __name__ == "__main__":
    main()
