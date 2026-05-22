"""
Modal A10G fallback PoC for SoulX-FlashHead 1.3B Lite

Edward Python 3.14 + PyTorch CUDA wheel 缺 → 走 Modal A10G fallback
(sulima #5 verdict 已 cover · daily driver 仍 prefer 本機 · PoC 一次性 OK)

Run:
  cd castle-voice-engine
  modal deploy poc/modal_soulx_flashhead.py
  modal run poc/modal_soulx_flashhead.py::run_demo

Cost estimate:
  A10G $1.10/hr · cold start ~10 min · single inference ~30-60s
  → PoC 試 1 hr = $1-2

Architecture:
  1. Image build:
     - Python 3.11 + PyTorch 2.7 cu124
     - SoulX-FlashHead requirements
     - Clone SoulX-FlashHead GitHub code to /soulx-code
  2. Model weights via Modal Volume (mount /models)
     - SoulX-FlashHead-1_3B (13.67 GB) - one-time HF download into Volume
     - wav2vec2-base-960h (~360 MB) - same
  3. run_inference function:
     - Take cond_image bytes + audio bytes
     - Call generate_video.py via subprocess
     - Return output video bytes

Edward 邊界 (sulima #5 spec):
  - Edward 自己樣本: OK
  - Sally: NEVER (hard rule)
  - Qiana: only if she opts in
  - Outputs: local download only (not persist on Modal)
"""

from __future__ import annotations

import modal

# === Image: Python 3.11 + CUDA 12.4 PyTorch + SoulX deps ===
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "libsm6", "libxext6")
    # PyTorch CUDA 12.6 (cu124 only goes up to 2.6.0 · 2.7.1 needs cu126)
    .pip_install(
        "torch==2.7.1",
        "torchvision==0.22.1",
        "torchaudio==2.7.1",
        index_url="https://download.pytorch.org/whl/cu126",
    )
    # Stage 1: core ML stack (split to avoid pip resolution-too-deep)
    .pip_install(
        "transformers==4.57.3",
        "tokenizers==0.22.1",
        "diffusers==0.35.2",
        "accelerate==1.10.1",
        "safetensors==0.5.3",
        "huggingface_hub==0.34.4",
        "numpy==1.26.4",
    )
    # Stage 2: image / video stack
    .pip_install(
        "opencv-python-headless==4.12.0.88",
        "mediapipe==0.10.9",
        "decord==0.6.0",
        "imageio==2.37.0",
        "imageio-ffmpeg==0.6.0",
        "scikit-image==0.25.2",
        "Pillow==11.0.0",
    )
    # Stage 3: audio stack
    .pip_install(
        "librosa==0.10.2.post1",
        "pyloudnorm==0.1.1",
        "scipy==1.15.2",
    )
    # Stage 4: utils
    .pip_install(
        "tqdm==4.67.1",
        "easydict==1.13",
        "ftfy==6.3.1",
        "loguru==0.7.3",
        "einops==0.8.0",
        "omegaconf==2.3.0",
    )
    # flash_attn requires CUDA toolkit + ninja for build · use prebuilt wheel if available
    # A10G is Ampere (SM86) · flash_attn 2.5+ supports Ampere
    .pip_install(
        "flash-attn==2.8.0.post2",
        extra_options="--no-build-isolation",
    )
    # Clone SoulX-FlashHead inference code
    .run_commands(
        "git clone --depth 1 https://github.com/Soul-AILab/SoulX-FlashHead.git /soulx-code",
        "ls /soulx-code/",
    )
)

# === Modal Volume: model weights cache ===
# First run downloads 13.67 GB SoulX + 360 MB wav2vec2; subsequent runs hit volume cache
models_vol = modal.Volume.from_name("soulx-flashhead-models", create_if_missing=True)

app = modal.App("soulx-flashhead-poc")


@app.function(
    image=image,
    gpu="A10G",  # 24 GB VRAM
    timeout=1800,  # 30 minutes
    volumes={"/models": models_vol},
)
def ensure_models_cached() -> dict:
    """First-time helper: download SoulX-FlashHead + wav2vec2 into Modal Volume."""
    import os
    from pathlib import Path
    from huggingface_hub import snapshot_download

    out = {}

    soulx_target = Path("/models/soulx-flashhead-1.3b")
    if not soulx_target.exists() or not any(soulx_target.iterdir()):
        print("[download] Soul-AILab/SoulX-FlashHead-1_3B (13.67 GB)...")
        soulx_target.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id="Soul-AILab/SoulX-FlashHead-1_3B",
            local_dir=str(soulx_target),
        )
        out["soulx"] = "downloaded"
    else:
        out["soulx"] = "cached"

    wav2vec_target = Path("/models/wav2vec2-base-960h")
    if not wav2vec_target.exists() or not any(wav2vec_target.iterdir()):
        print("[download] facebook/wav2vec2-base-960h (~360 MB)...")
        wav2vec_target.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id="facebook/wav2vec2-base-960h",
            local_dir=str(wav2vec_target),
        )
        out["wav2vec2"] = "downloaded"
    else:
        out["wav2vec2"] = "cached"

    # Inventory
    for name, path in [("soulx", soulx_target), ("wav2vec2", wav2vec_target)]:
        size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        n_files = sum(1 for p in path.rglob("*") if p.is_file())
        out[f"{name}_inventory"] = {"files": n_files, "size_mb": round(size / 1024 / 1024, 1)}

    # Commit Volume so cache persists for next inference
    models_vol.commit()
    return out


@app.function(
    image=image,
    gpu="A10G",
    timeout=1800,
    volumes={"/models": models_vol},
)
def run_inference(
    cond_image_bytes: bytes,
    audio_bytes: bytes,
    model_type: str = "lite",
) -> dict:
    """
    Run SoulX-FlashHead inference on given conditioning image + audio.

    Args:
        cond_image_bytes: PNG/JPG bytes of reference face image
        audio_bytes: WAV bytes (16kHz mono PCM16 preferred)
        model_type: "lite" (fast · 1.3B) or "pro" (high quality)

    Returns:
        {
            "ok": bool,
            "video_bytes": bytes | None,   # MP4 video bytes
            "stdout": str,
            "stderr": str,
            "returncode": int,
            "video_size_mb": float | None,
            "elapsed_s": float,
        }
    """
    import subprocess
    import time
    from pathlib import Path

    # Ensure models cached first (no-op if already)
    print("[step 1] Ensure models cached...")
    cache_result = ensure_models_cached.local()
    print(f"  cache result: {cache_result}")

    # Stage inputs
    inputs_dir = Path("/tmp/inputs")
    outputs_dir = Path("/tmp/outputs")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    cond_path = inputs_dir / "cond.png"
    audio_path = inputs_dir / "audio.wav"
    cond_path.write_bytes(cond_image_bytes)
    audio_path.write_bytes(audio_bytes)
    print(f"[step 2] inputs staged · cond={cond_path.stat().st_size} bytes · audio={audio_path.stat().st_size} bytes")

    # Run inference via generate_video.py
    cmd = [
        "python", "/soulx-code/generate_video.py",
        "--ckpt_dir", "/models/soulx-flashhead-1.3b/Model_Lite",
        "--wav2vec_dir", "/models/wav2vec2-base-960h",
        "--model_type", model_type,
        "--cond_image", str(cond_path),
        "--audio_path", str(audio_path),
        "--audio_encode_mode", "stream",
        "--save_dir", str(outputs_dir),
    ]
    print(f"[step 3] launching inference: {' '.join(cmd)}")
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd="/soulx-code")
    elapsed = time.time() - t0
    print(f"[step 4] inference done · returncode={proc.returncode} · elapsed={elapsed:.1f}s")
    print(f"  stdout (last 500 chars): {proc.stdout[-500:]}")
    if proc.stderr:
        print(f"  stderr (last 500 chars): {proc.stderr[-500:]}")

    # Find output video
    video_bytes = None
    video_size_mb = None
    for candidate in outputs_dir.rglob("*.mp4"):
        video_bytes = candidate.read_bytes()
        video_size_mb = round(len(video_bytes) / 1024 / 1024, 2)
        print(f"  found video: {candidate} · {video_size_mb} MB")
        break

    return {
        "ok": proc.returncode == 0 and video_bytes is not None,
        "video_bytes": video_bytes,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
        "returncode": proc.returncode,
        "video_size_mb": video_size_mb,
        "elapsed_s": round(elapsed, 1),
    }


@app.local_entrypoint()
def run_demo():
    """Local entrypoint: ship Edward's 5/21 audio + girl.png to Modal · save output."""
    from pathlib import Path

    here = Path(__file__).resolve().parent
    repo_root = here.parent

    # Step 1: ensure models cached (one-time)
    print("=== Step 1: ensure models cached on Modal Volume ===")
    cache = ensure_models_cached.remote()
    print(f"cache status: {cache}")

    # Step 2: prepare inputs
    print()
    print("=== Step 2: prepare inputs ===")
    # cond_image: use girl.png from cloned repo (we'll need to either ship it or
    # use a path · simpler: read from local clone)
    cond_path = repo_root / "external" / "soulx-flashhead-code" / "examples" / "girl.png"
    audio_path = here / "edward_5_21_16k_mono.wav"
    print(f"  cond_image: {cond_path} ({cond_path.stat().st_size} bytes)")
    print(f"  audio: {audio_path} ({audio_path.stat().st_size} bytes)")
    cond_bytes = cond_path.read_bytes()
    audio_bytes = audio_path.read_bytes()

    # Step 3: run inference
    print()
    print("=== Step 3: run inference on Modal A10G ===")
    result = run_inference.remote(cond_bytes, audio_bytes, model_type="lite")
    print(f"  ok: {result['ok']}")
    print(f"  returncode: {result['returncode']}")
    print(f"  elapsed: {result['elapsed_s']}s")
    print(f"  video_size_mb: {result['video_size_mb']}")
    if result.get('stderr'):
        print(f"  stderr tail: {result['stderr'][-300:]}")

    # Step 4: save output
    if result["ok"] and result["video_bytes"]:
        out_path = here / "edward_5_21_sophie_lily_demo.mp4"
        out_path.write_bytes(result["video_bytes"])
        print()
        print(f"  ✓ saved: {out_path}")
        print(f"  open with: start {out_path}")
    else:
        print()
        print("  ✗ inference failed · see stderr above")
