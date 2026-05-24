# breeze_poc/app_musetalk.py
# Voice Path v0.7 · MuseTalk v1.5 lipsync · Modal app
# (c) 2026 Edward / BeyondPath
# MuseTalk v1.5 by Lyra Lab, Tencent Music Entertainment (MIT License)
# https://github.com/TMElyralab/MuseTalk
#
# Dependencies attribution:
#   - OpenAI Whisper (MIT)
#   - IDEA-Research DWPose (Apache-2.0)
#   - ft-mse-vae (CreativeML Open RAIL-M · Track B audit required for commercial use)
#   - S3FD (license verification pending)
#
# Tested matrix (from MuseTalk official README + requirements.txt + inference.sh):
#   - Python 3.10
#   - CUDA 11.7 client + Modal host driver 580 (NVIDIA forward compat OK)
#   - torch 2.0.1+cu117
#   - GPU: A10G ($1.10/hr · scale-to-zero · scaledown_window=60)
#   - No flash-attn / no source-build wheels
#
# Architecture (Edward 2026-05-23 拍板):
#   聽 = Breeze ASR-25 (castle-voice-engine-breeze-poc)
#   說 = OpenAI gpt-realtime-2 (castle/server/realtime_endpoints.py · marin voice + Sophie persona)
#   嘴 = MuseTalk (this app)
#
# Endpoints:
#   GET  /musetalk/health        - warm + model status
#   POST /musetalk/enroll        - upload reference face (subject_guard required)
#   WS   /musetalk/stream        - audio chunks in, H264 video frames out

import modal

# ---------------------------------------------------------------------------
# Modal image · independent from breeze (different python + torch pin)
# ---------------------------------------------------------------------------

musetalk_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "libgl1", "libglib2.0-0", "wget")
    .pip_install(
        "torch==2.0.1",
        "torchvision==0.15.2",
        "torchaudio==2.0.2",
        extra_index_url="https://download.pytorch.org/whl/cu117",
    )
    .pip_install(
        # MuseTalk official requirements.txt (pinned)
        "diffusers==0.30.2",
        "accelerate==0.28.0",
        "numpy==1.23.5",
        "tensorflow==2.12.0",
        "tensorboard==2.12.0",
        "opencv-python==4.9.0.80",
        "soundfile==0.12.1",
        "transformers==4.39.2",
        "huggingface_hub==0.30.2",
        "einops==0.8.1",
        "librosa==0.11.0",  # Phase 6 (calcifer): MuseTalk audio_processor depends on librosa
        "gdown",
        "requests",
        "imageio[ffmpeg]",
        "omegaconf",
        "ffmpeg-python",
        "moviepy",
        # FastAPI server (kept inside main image so the asgi_app share cache)
        "fastapi>=0.110,<0.116",
        "uvicorn[standard]>=0.29,<0.31",
        "pydantic>=2.0",
        "python-multipart>=0.0.9",
    )
    .run_commands(
        "cd /root && git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git",
        # Phase 7a (2026-05-23 calcifer): MMLab ecosystem for preprocessing.get_landmark_and_bbox
        # Official MuseTalk README install spec (must use mim, not pip, for cross-pkg compat):
        #   pip install --no-cache-dir -U openmim
        #   mim install mmengine
        #   mim install "mmcv==2.0.1"
        #   mim install "mmdet==3.1.0"
        #   mim install "mmpose==1.1.0"
        # mmcv 2.0.1 needs Linux cu117 prebuilt wheel; mim resolves automatically.
        "pip install --no-cache-dir -U openmim",
        "mim install mmengine",
        "mim install mmcv==2.0.1",
        "mim install mmdet==3.1.0",
        "mim install mmpose==1.1.0",
    )
)

app = modal.App("castle-voice-engine-musetalk-poc")

MUSETALK_AUTH_TOKEN_SECRET = modal.Secret.from_name("musetalk-poc-auth")
HF_SECRET = modal.Secret.from_name("huggingface", required_keys=[])

# Persisted volume so model weights (~10-15 GB) only download once
MUSETALK_VOLUME = modal.Volume.from_name("musetalk-weights", create_if_missing=True)


# ---------------------------------------------------------------------------
# Inference class
# ---------------------------------------------------------------------------


@app.cls(
    image=musetalk_image,
    gpu="A10G",
    memory=24576,
    timeout=900,
    scaledown_window=60,
    secrets=[MUSETALK_AUTH_TOKEN_SECRET, HF_SECRET],
    volumes={"/weights": MUSETALK_VOLUME},
    min_containers=0,
    # v0.7 P2.1 attempt 1 (2026-05-24 calcifer): enable_memory_snapshot=True tried · NO-GO
    # Modal memory snapshot does NOT support GPU state in 1.4.2 · cold-start stayed 74s (no improvement)
    # Reverted per Edward P2.1 red-line: snapshot fail → revert immediately, do not push.
    # See lesson_2026-05-24_modal-snapshot-gpu-not-supported.md (to be written)
)
class MuseTalkRunner:
    """MuseTalk lipsync inference · cold-start ~5-8s once weights cached."""

    @modal.enter()
    def load_model(self):
        import os
        import sys
        import time

        sys.path.insert(0, "/root/MuseTalk")

        t0 = time.time()
        print("[MuseTalk] cold start begin", flush=True)

        # Ensure weights exist on volume (first run downloads ~10-15 GB)
        # Phase 5 fix (2026-05-23 calcifer): use sentinel file instead of dir exist check
        # because empty dir shells from failed previous downloads pass the os.path.exists check
        sentinel = "/weights/.muse_v15_complete"
        weights_ready = os.path.exists(sentinel)

        if not weights_ready:
            # Phase 6 (2026-05-23 calcifer): Python-native huggingface_hub snapshot_download
            # replaces broken download_weights.sh (silent-fail due to hf-mirror.com unreachable
            # from Modal US datacenters + huggingface-cli exit 0 on partial fail).
            # Reproduces every line of download_weights.sh in Python (6 HF repos + gdown + curl).
            print("[MuseTalk] weights sentinel missing, downloading via huggingface_hub", flush=True)
            os.makedirs("/weights", exist_ok=True)
            for sub in ("musetalk", "musetalkV15", "syncnet", "dwpose",
                        "face-parse-bisent", "sd-vae", "whisper"):
                os.makedirs(f"/weights/{sub}", exist_ok=True)

            from huggingface_hub import snapshot_download

            # 1) MuseTalk v1.0 + v1.5 (same repo, allow_patterns scopes the download)
            print("[MuseTalk] [1/6] TMElyralab/MuseTalk (musetalk/ + musetalkV15/)", flush=True)
            snapshot_download(
                repo_id="TMElyralab/MuseTalk",
                local_dir="/weights",
                allow_patterns=[
                    "musetalk/musetalk.json", "musetalk/pytorch_model.bin",
                    "musetalkV15/musetalk.json", "musetalkV15/unet.pth",
                ],
            )

            # 2) SD-VAE-ft-mse (config.json + diffusion_pytorch_model.bin)
            print("[MuseTalk] [2/6] stabilityai/sd-vae-ft-mse", flush=True)
            snapshot_download(
                repo_id="stabilityai/sd-vae-ft-mse",
                local_dir="/weights/sd-vae",
                allow_patterns=["config.json", "diffusion_pytorch_model.bin"],
            )

            # 3) Whisper-tiny (3 files for MuseTalk audio2feature path)
            print("[MuseTalk] [3/6] openai/whisper-tiny", flush=True)
            snapshot_download(
                repo_id="openai/whisper-tiny",
                local_dir="/weights/whisper",
                allow_patterns=["config.json", "pytorch_model.bin", "preprocessor_config.json"],
            )

            # 4) DWPose
            print("[MuseTalk] [4/6] yzd-v/DWPose", flush=True)
            snapshot_download(
                repo_id="yzd-v/DWPose",
                local_dir="/weights/dwpose",
                allow_patterns=["dw-ll_ucoco_384.pth"],
            )

            # 5) SyncNet (ByteDance/LatentSync)
            print("[MuseTalk] [5/6] ByteDance/LatentSync (syncnet)", flush=True)
            snapshot_download(
                repo_id="ByteDance/LatentSync",
                local_dir="/weights/syncnet",
                allow_patterns=["latentsync_syncnet.pt"],
            )

            # 6) Face-parse-bisent (gdown + resnet18 curl) -- non-HF sources
            import subprocess
            face_parse_target = "/weights/face-parse-bisent/79999_iter.pth"
            if not os.path.exists(face_parse_target):
                print("[MuseTalk] [6a/6] face-parse-bisent via gdown", flush=True)
                # gdown v5+ removed --id; use positional URL form (works both gdown v4 + v5)
                gd = subprocess.run(
                    ["gdown",
                     "https://drive.google.com/uc?id=154JgKpzCPW82qINcVieuPH3fZ2e0P812",
                     "-O", face_parse_target, "--no-cookies"],
                    capture_output=True, text=True, timeout=600,
                )
                if gd.returncode != 0:
                    print("[MuseTalk] gdown stderr:", gd.stderr[-800:], flush=True)
                    print("[MuseTalk] gdown stdout:", gd.stdout[-800:], flush=True)
                    raise RuntimeError(f"gdown face-parse-bisent failed rc={gd.returncode}")
                # Verify gdown actually downloaded a non-trivial file (defense against silent fail)
                if not os.path.exists(face_parse_target) or os.path.getsize(face_parse_target) < 10*1024*1024:
                    actual = os.path.getsize(face_parse_target) if os.path.exists(face_parse_target) else 0
                    print(f"[MuseTalk] gdown stdout:", gd.stdout[-800:], flush=True)
                    raise RuntimeError(f"gdown produced suspicious file size {actual} bytes (expected ~50MB)")
                print(f"[MuseTalk] gdown wrote {os.path.getsize(face_parse_target)/1024/1024:.1f} MB", flush=True)

            resnet_target = "/weights/face-parse-bisent/resnet18-5c106cde.pth"
            if not os.path.exists(resnet_target):
                # urllib.request beats subprocess curl - no apt rebuild + native to image python
                print("[MuseTalk] [6b/6] resnet18 via urllib from pytorch.org", flush=True)
                import urllib.request
                urllib.request.urlretrieve(
                    "https://download.pytorch.org/models/resnet18-5c106cde.pth",
                    resnet_target,
                )
                size_mb = os.path.getsize(resnet_target) / 1024 / 1024
                print(f"[MuseTalk] resnet18 downloaded {size_mb:.1f} MB", flush=True)

            # Diagnostic: list actual contents post-download
            for path in ["/weights"]:
                ls = subprocess.run(["ls", "-la", path], capture_output=True, text=True)
                print(f"[MuseTalk] DIAG ls {path}", flush=True)
                print(ls.stdout, flush=True)
                find = subprocess.run(
                    ["find", path, "-maxdepth", "3", "-type", "f", "-size", "+1k"],
                    capture_output=True, text=True,
                )
                print(f"[MuseTalk] DIAG files >1k under {path}", flush=True)
                print(find.stdout, flush=True)

            # Verify critical model files exist before sealing sentinel
            # (Phase 5 list + Phase 6 additions covering all 6 sources)
            critical = [
                "/weights/musetalkV15/unet.pth",
                "/weights/musetalkV15/musetalk.json",
                "/weights/sd-vae/config.json",
                "/weights/sd-vae/diffusion_pytorch_model.bin",
                "/weights/whisper/pytorch_model.bin",
                "/weights/whisper/config.json",
                "/weights/dwpose/dw-ll_ucoco_384.pth",
                "/weights/syncnet/latentsync_syncnet.pt",
                "/weights/face-parse-bisent/79999_iter.pth",
                "/weights/face-parse-bisent/resnet18-5c106cde.pth",
            ]
            missing = [p for p in critical if not os.path.exists(p)]
            if missing:
                raise RuntimeError(f"critical model files missing after download: {missing}")

            with open(sentinel, "w") as f:
                f.write("v15 download complete - calcifer phase 6 HF native - 2026-05-23")
            MUSETALK_VOLUME.commit()
            print("[MuseTalk] sentinel written + volume committed", flush=True)
        else:
            print("[MuseTalk] sentinel found, skip download", flush=True)

        # Critical: MuseTalk internal code uses hardcoded relative path "models/sd-vae"
        # So we must (a) chdir to /root/MuseTalk and (b) symlink /root/MuseTalk/models -> /weights
        if not os.path.lexists("/root/MuseTalk/models"):
            os.symlink("/weights", "/root/MuseTalk/models")
            print("[MuseTalk] symlink /root/MuseTalk/models -> /weights created", flush=True)
        elif os.path.islink("/root/MuseTalk/models"):
            print("[MuseTalk] symlink already in place", flush=True)
        else:
            # real dir from download_weights.sh exists, replace with symlink to volume
            import shutil
            shutil.rmtree("/root/MuseTalk/models")
            os.symlink("/weights", "/root/MuseTalk/models")
            print("[MuseTalk] replaced real dir with symlink -> /weights", flush=True)

        os.chdir("/root/MuseTalk")
        weights_dir = "/weights/musetalkV15"

        # Lazy import after weights ready
        # Phase 6 (2026-05-23): load_all_model returns 3 values (vae, unet, pe); audio_processor
        # is a separate class loaded from local whisper-tiny dir to avoid HF hub network call
        from musetalk.utils.utils import load_all_model
        from musetalk.utils.audio_processor import AudioProcessor

        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=f"{weights_dir}/unet.pth",
            unet_config=f"{weights_dir}/musetalk.json",
            device="cuda",
        )
        # AudioProcessor uses transformers AutoFeatureExtractor; point at local whisper dir
        self.audio_processor = AudioProcessor(feature_extractor_path="/weights/whisper")
        print("[MuseTalk] models loaded: vae + unet + pe + audio_processor", flush=True)

        # Phase 7a (2026-05-23 calcifer): mmpose now installed via mim; build full Sophie
        # reference cache at cold-start so generate_video_chunk() is O(audio_length).
        # Steps cached:
        #   1) bbox + frame via get_landmark_and_bbox (single-image mode -> two-element list cycle)
        #   2) crop+resize 256x256 -> vae.get_latents_for_unet -> input_latent_list_cycle
        #   3) FaceParsing instance (needed for v15 get_image blending)
        #   4) Whisper encoder (frozen, fp16)
        # Mirrors scripts/inference.py main() but for a single reference image.
        self.sophie_ready = False
        self.sophie_coord_list_cycle = None
        self.sophie_frame_list_cycle = None
        self.sophie_input_latent_list_cycle = None
        self.fp = None
        self.whisper = None
        self.weight_dtype = None
        self.timesteps = None

        # v3.3 (2026-05-24) · Phase 3a · dynamic reference loading
        # 預設預載 idle (待機動畫 · 解 Edward「短 audio + 長講話動畫」問題)
        # 其他 16 個 state · lazy load on first request · cache in self.references
        self.references = {}  # state -> {coord_list_cycle, frame_list_cycle, input_latent_list_cycle}

        try:
            import torch
            import cv2
            import copy
            import numpy as np
            from musetalk.utils.preprocessing import get_landmark_and_bbox, coord_placeholder
            from musetalk.utils.face_parsing import FaceParsing
            from transformers import WhisperModel

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.weight_dtype = self.unet.model.dtype
            self.timesteps = torch.tensor([0], device=device)
            self._device = device

            # Move models to device + dtype
            self.pe = self.pe.to(device)
            self.vae.vae = self.vae.vae.to(device)
            self.unet.model = self.unet.model.to(device)

            # Whisper encoder for downstream get_whisper_chunk
            self.whisper = WhisperModel.from_pretrained("/weights/whisper")
            self.whisper = self.whisper.to(device=device, dtype=self.weight_dtype).eval()
            self.whisper.requires_grad_(False)
            print("[MuseTalk] Whisper encoder loaded", flush=True)

            # Face parsing for v15 blending (jaw mode default)
            self.fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)
            print("[MuseTalk] FaceParsing initialized", flush=True)

            # 預載 default reference (idle · 最常用)
            self._load_reference("idle")
            if "idle" in self.references:
                self.sophie_ready = True
                # legacy alias · 給原 generate_video_chunk 用 (Phase 3b 才會 refactor 完整動態)
                ref = self.references["idle"]
                self.sophie_frame_list_cycle = ref["frame_list_cycle"]
                self.sophie_coord_list_cycle = ref["coord_list_cycle"]
                self.sophie_input_latent_list_cycle = ref["input_latent_list_cycle"]
                print(f"[MuseTalk] default reference 'idle' ready", flush=True)
            else:
                print(f"[MuseTalk] WARN default reference 'idle' failed to load", flush=True)
        except Exception as e:
            import traceback
            print(f"[MuseTalk] precompute FAILED: {type(e).__name__}: {e}", flush=True)
            print(traceback.format_exc(), flush=True)

        elapsed = round(time.time() - t0, 1)
        print(f"[MuseTalk] ready in {elapsed}s (sophie_ready={self.sophie_ready})", flush=True)


    def _load_reference(self, state: str):
        """Lazy-load reference video frames + bbox + latents for given state.
        state: idle / greeting / happy / apologetic / speaking / etc.
        falls back to idle if state file not found.
        Caches result in self.references[state].
        """
        import os
        if state in self.references:
            return self.references[state]
        import cv2
        import torch
        from musetalk.utils.preprocessing import get_landmark_and_bbox, coord_placeholder

        ref_path = f"/weights/assets/references/{state}.mp4"
        if not os.path.exists(ref_path):
            if state == "idle":
                # 完全沒 idle 也 fallback 到 static png
                if os.path.exists("/weights/assets/sophie-reference.png"):
                    print(f"[MuseTalk] state '{state}' video missing, using static image fallback", flush=True)
                    return self._load_from_paths(state, ["/weights/assets/sophie-reference.png"])
                return None
            print(f"[MuseTalk] state '{state}' video not found, fallback to idle", flush=True)
            return self._load_reference("idle")

        # v3.3.1 · 修 Edward catch「動畫加速 + 重複動作」
        # 不 step 抽稀 (保原速) · 直接抽全部 frames (上限 200 ~ 8 秒 @ 25fps)
        cap = cv2.VideoCapture(ref_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        max_frames = min(total_frames, 200)  # 上限 200 (避免太長 OOM)
        tmp_dir = f"/tmp/sophie_ref_{state}"
        os.makedirs(tmp_dir, exist_ok=True)
        paths = []
        for i in range(max_frames):
            ret, frame = cap.read()
            if not ret:
                break
            p = f"{tmp_dir}/frame_{i:04d}.png"
            cv2.imwrite(p, frame)
            paths.append(p)
        cap.release()
        print(f"[MuseTalk] state '{state}' extracted {len(paths)} frames (保原速 · 不抽稀)", flush=True)
        return self._load_from_paths(state, paths)

    def _load_from_paths(self, state: str, paths: list):
        """Run face detection + latent precompute on given image paths."""
        import cv2
        from musetalk.utils.preprocessing import get_landmark_and_bbox, coord_placeholder
        coord_list, frame_list = get_landmark_and_bbox(paths, 0)
        if not coord_list or coord_list[0] == coord_placeholder:
            print(f"[MuseTalk] state '{state}' face detection failed", flush=True)
            return None
        extra_margin = 10
        input_latent_list = []
        new_coord_list = []
        for bbox, frame in zip(coord_list, frame_list):
            if bbox == coord_placeholder:
                new_coord_list.append(bbox)
                continue
            x1, y1, x2, y2 = bbox
            y2 = min(y2 + extra_margin, frame.shape[0])
            new_coord_list.append([x1, y1, x2, y2])
            crop_frame = frame[y1:y2, x1:x2]
            crop_frame = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            latents = self.vae.get_latents_for_unet(crop_frame)
            input_latent_list.append(latents)
        # v3.3.2 · Edward 提案 · 動作類 = 「情緒一次 + 接 idle loop」
        # 避免 freeze 末幀只動嘴 10 秒、避免動作重複播
        # 可 loop 類 · ping-pong cycle (待機 / 撥頭髮自然 loop)
        # 動作類 · 動作做完 + 接 idle ping-pong loop (身體律動不斷)
        LOOPABLE_STATES = {"idle", "idle-2", "idle-3", "idle-4", "stroke-hair", "speaking"}
        if state in LOOPABLE_STATES:
            frame_list_cycle = frame_list + frame_list[::-1]
            coord_list_cycle = new_coord_list + new_coord_list[::-1]
            input_latent_list_cycle = input_latent_list + input_latent_list[::-1]
            cycle_mode = "ping-pong loop"
        else:
            # 動作類 · 情緒做完接 idle (Edward 5/24 提案 · 不卡末幀)
            idle_ref = self.references.get("idle")
            if idle_ref is None:
                # idle 還沒載 · fallback 凍結末幀 (保險)
                tail_pad = 200
                frame_list_cycle = frame_list + [frame_list[-1]] * tail_pad
                coord_list_cycle = new_coord_list + [new_coord_list[-1]] * tail_pad
                input_latent_list_cycle = input_latent_list + [input_latent_list[-1]] * tail_pad
                cycle_mode = "forward + freeze (idle not cached)"
            else:
                # 動作一次 + idle ping-pong loop 接力
                idle_f = idle_ref["frame_list_cycle"]
                idle_c = idle_ref["coord_list_cycle"]
                idle_l = idle_ref["input_latent_list_cycle"]
                frame_list_cycle = frame_list + idle_f
                coord_list_cycle = new_coord_list + idle_c
                input_latent_list_cycle = input_latent_list + idle_l
                cycle_mode = f"action({len(frame_list)}f) + idle loop({len(idle_f)}f)"

        ref = {
            "frame_list_cycle": frame_list_cycle,
            "coord_list_cycle": coord_list_cycle,
            "input_latent_list_cycle": input_latent_list_cycle,
        }
        self.references[state] = ref
        print(f"[MuseTalk] state '{state}' cached (latents={len(input_latent_list)} cycle={len(ref['frame_list_cycle'])} mode={cycle_mode})", flush=True)
        return ref

    @modal.method()
    def warm(self):
        return {
            "status": "ready",
            "model": "MuseTalk v1.5",
            "license": "MIT (Lyra Lab/Tencent Music Entertainment)",
            "sophie_reference_cached": self.sophie_ready,
        }

    @modal.method()
    def generate_video_chunk(self, audio_pcm_bytes: bytes, fps: int = 25, reference_state: str = "idle"):
        # v3.3 Phase 3a · reference_state 動態切換 (idle / greeting / happy / apologetic / 等)
        # Phase 7a (2026-05-23 calcifer): full pipeline ported from scripts/inference.py.
        import os, io, time, tempfile, subprocess, copy
        import numpy as np
        import torch, cv2, soundfile as sf
        from tqdm import tqdm

        # v3.3 · 動態切換 reference state
        ref = self._load_reference(reference_state)
        if ref:
            self.sophie_frame_list_cycle = ref["frame_list_cycle"]
            self.sophie_coord_list_cycle = ref["coord_list_cycle"]
            self.sophie_input_latent_list_cycle = ref["input_latent_list_cycle"]
            print(f"[MuseTalk gen] reference_state='{reference_state}' loaded", flush=True)

        if not self.sophie_ready:
            return {"error": "sophie reference not cached", "video_bytes": b"", "frame_count": 0, "fps": fps}

        from musetalk.utils.utils import datagen
        from musetalk.utils.blending import get_image

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        audio_arr, sr = sf.read(io.BytesIO(audio_pcm_bytes), dtype="float32")
        if sr != 16000:
            raise ValueError(f"Expected 16kHz PCM, got {sr}Hz")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav_f:
            tmp_wav = tmp_wav_f.name
        sf.write(tmp_wav, audio_arr, sr, subtype="PCM_16")
        print(f"[MuseTalk gen] wav dumped: {tmp_wav} ({len(audio_arr)/sr:.2f}s)", flush=True)

        try:
            t0 = time.time()
            whisper_input_features, librosa_length = self.audio_processor.get_audio_feature(
                tmp_wav, weight_dtype=self.weight_dtype
            )
            whisper_chunks = self.audio_processor.get_whisper_chunk(
                whisper_input_features, device, self.weight_dtype, self.whisper, librosa_length,
                fps=fps, audio_padding_length_left=2, audio_padding_length_right=2,
            )
            video_num = len(whisper_chunks)
            print(f"[MuseTalk gen] audio features: chunks={video_num} ({(time.time()-t0)*1000:.0f}ms)", flush=True)

            # Phase 7a (calcifer): batch_size 8 -> 2 (A10G 22GB OOM with v1.5 unet+vae at bs=8)
            batch_size = 2
            gen = datagen(whisper_chunks=whisper_chunks,
                          vae_encode_latents=self.sophie_input_latent_list_cycle,
                          batch_size=batch_size, delay_frame=0, device=str(device))
            res_frame_list = []
            total = int(np.ceil(float(video_num) / batch_size))
            t1 = time.time()
            for i, (whisper_batch, latent_batch) in enumerate(tqdm(gen, total=total, desc="inference")):
                audio_feature_batch = self.pe(whisper_batch.to(device))
                latent_batch = latent_batch.to(device=device, dtype=self.unet.model.dtype)
                pred_latents = self.unet.model(latent_batch, self.timesteps, encoder_hidden_states=audio_feature_batch).sample
                pred_latents = pred_latents.to(device=device, dtype=self.vae.vae.dtype)
                recon = self.vae.decode_latents(pred_latents)
                for res_frame in recon:
                    res_frame_list.append(res_frame)
                # Phase 7a (calcifer): free intermediate tensors to avoid OOM accumulation
                del pred_latents, recon, audio_feature_batch
                torch.cuda.empty_cache()
            print(f"[MuseTalk gen] unet+vae: frames={len(res_frame_list)} ({(time.time()-t1)*1000:.0f}ms)", flush=True)

            tmp_frames_dir = tempfile.mkdtemp(prefix="musetalk_frames_")
            t2 = time.time()
            for i, res_frame in enumerate(res_frame_list):
                bbox = self.sophie_coord_list_cycle[i % len(self.sophie_coord_list_cycle)]
                ori_frame = copy.deepcopy(self.sophie_frame_list_cycle[i % len(self.sophie_frame_list_cycle)])
                x1, y1, x2, y2 = bbox
                try:
                    res_frame_resized = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
                except Exception as resize_err:
                    print(f"[MuseTalk gen] resize fail i={i}: {resize_err}", flush=True)
                    continue
                combine_frame = get_image(ori_frame, res_frame_resized, [x1, y1, x2, y2], mode="jaw", fp=self.fp)
                cv2.imwrite(f"{tmp_frames_dir}/{str(i).zfill(8)}.png", combine_frame)
            print(f"[MuseTalk gen] blending done ({(time.time()-t2)*1000:.0f}ms)", flush=True)

            tmp_silent = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
            tmp_final = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
            # v3.0 (2026-05-24) · 修新版蘇菲照片 941x1672 寬度奇數 · x264 要偶數 · 加 scale trunc
            cmd_v = ["ffmpeg","-y","-v","warning","-r",str(fps),"-f","image2",
                     "-i",f"{tmp_frames_dir}/%08d.png","-vcodec","libx264",
                     "-vf","scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p","-crf","18",tmp_silent]
            r1 = subprocess.run(cmd_v, capture_output=True, text=True, timeout=120)
            if r1.returncode != 0:
                print(f"[MuseTalk gen] ffmpeg v stderr: {r1.stderr[-500:]}", flush=True)
                raise RuntimeError(f"ffmpeg video encode failed rc={r1.returncode}")

            cmd_a = ["ffmpeg","-y","-v","warning","-i",tmp_wav,"-i",tmp_silent,
                     "-c:v","copy","-c:a","aac","-shortest",tmp_final]
            r2 = subprocess.run(cmd_a, capture_output=True, text=True, timeout=120)
            if r2.returncode != 0:
                print(f"[MuseTalk gen] ffmpeg a stderr: {r2.stderr[-500:]}", flush=True)
                raise RuntimeError(f"ffmpeg audio mux failed rc={r2.returncode}")

            with open(tmp_final, "rb") as f:
                mp4_bytes = f.read()
            print(f"[MuseTalk gen] mp4 ready: {len(mp4_bytes)/1024:.1f} KB, elapsed={(time.time()-t0):.2f}s", flush=True)

            return {"video_bytes": mp4_bytes, "frame_count": len(res_frame_list), "fps": fps, "duration_s": len(audio_arr)/sr}
        finally:
            try:
                os.unlink(tmp_wav)
            except Exception:
                pass

    # ---------------------------------------------------------------
    # v0.7 P2 . Phase 1 . chunked streaming helpers (calcifer 2026-05-24)
    # ---------------------------------------------------------------
    # Design (verified by prev agent run a295d10a23926fb0c . Edward GO):
    #   - chunk = 12 frames @ 25fps = 0.48s (whisper hop align)
    #   - container = fMP4 (fragmented mp4 . MediaSource API friendly)
    #   - first segment carries init box (empty_moov)
    #   - PTS continuity via -output_ts_offset (seq * 0.48)
    #   - share reference cache + unet + vae (do not rebuild)
    #   - keep batch_size=2 (A10G OOM red-line)
    # The old generate_video_chunk() is kept untouched as fallback path.

    def _slice_audio(self, audio_arr, sr, seq, chunk_frames, fps):
        """Sample-level slice of float32 PCM audio for one chunk."""
        import numpy as np
        samples_per_chunk = int(round(sr * chunk_frames / fps))
        start = seq * samples_per_chunk
        end = start + samples_per_chunk
        if start >= len(audio_arr):
            return np.zeros((0,), dtype=audio_arr.dtype)
        return audio_arr[start:end]

    def _blend_frames(self, seg_res_frames, seg_idx_start):
        """Blend a list of unet-decoded face crops back onto reference frames."""
        import copy
        import cv2
        import numpy as np
        from musetalk.utils.blending import get_image

        out = []
        cyc_coord = self.sophie_coord_list_cycle
        cyc_frame = self.sophie_frame_list_cycle
        for j, res_frame in enumerate(seg_res_frames):
            abs_i = seg_idx_start + j
            bbox = cyc_coord[abs_i % len(cyc_coord)]
            ori_frame = copy.deepcopy(cyc_frame[abs_i % len(cyc_frame)])
            x1, y1, x2, y2 = bbox
            try:
                res_frame_resized = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
            except Exception as resize_err:
                print(f"[MuseTalk stream] resize fail abs_i={abs_i}: {resize_err}", flush=True)
                continue
            combine_frame = get_image(ori_frame, res_frame_resized, [x1, y1, x2, y2], mode="jaw", fp=self.fp)
            out.append(combine_frame)
        return out

    def _encode_fragment(self, seg_blended, seg_audio, sr, fps, seq, emit_init):
        """Encode one blended chunk + its audio slice as a fMP4 fragment."""
        import os, tempfile, subprocess, cv2
        import numpy as np
        import soundfile as sf

        if not seg_blended:
            return b""

        frame_dir = tempfile.mkdtemp(prefix=f"musetalk_seg_{seq:04d}_")
        try:
            for j, fr in enumerate(seg_blended):
                cv2.imwrite(f"{frame_dir}/{str(j).zfill(8)}.png", fr)

            audio_wav = os.path.join(frame_dir, "seg.wav")
            if seg_audio is not None and len(seg_audio) > 0:
                sf.write(audio_wav, seg_audio, sr, subtype="PCM_16")
            else:
                pad = np.zeros((int(sr * len(seg_blended) / fps),), dtype=np.float32)
                sf.write(audio_wav, pad, sr, subtype="PCM_16")

            out_path = os.path.join(frame_dir, f"seg_{seq:04d}.m4s")
            offset_s = seq * (len(seg_blended) / fps)
            frag_duration_us = str(int(round(len(seg_blended) / fps * 1_000_000)))

            cmd = [
                "ffmpeg", "-y", "-v", "warning",
                "-r", str(fps), "-f", "image2",
                "-i", f"{frame_dir}/%08d.png",
                "-i", audio_wav,
                "-output_ts_offset", str(offset_s),
                "-vcodec", "libx264",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                "-crf", "18",
                "-c:a", "aac",
                "-shortest",
                "-movflags", "+frag_keyframe+empty_moov+default_base_moof+separate_moof",
                "-frag_duration", frag_duration_us,
                "-f", "mp4",
                out_path,
            ]
            _ = emit_init  # unused in phase 1 (every fmp4 seg carries init box anyway)

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                print(f"[MuseTalk stream] ffmpeg seg {seq} stderr: {r.stderr[-400:]}", flush=True)
                raise RuntimeError(f"ffmpeg seg {seq} encode failed rc={r.returncode}")

            with open(out_path, "rb") as f:
                data = f.read()
            return data
        finally:
            try:
                import shutil
                shutil.rmtree(frame_dir, ignore_errors=True)
            except Exception:
                pass

    @modal.method()
    def generate_video_chunk_streaming(self, audio_pcm_bytes: bytes, fps: int = 25,
                                       reference_state: str = "idle", chunk_frames: int = 12,
                                       container_fmt: str = "fmp4"):
        """Streaming generator . yields one fMP4 fragment per chunk_frames.

        Yields dict with keys: seq, fmp4_bytes, frame_count, is_first, is_last, pts_offset_s.
        Shares reference cache + unet + vae with generate_video_chunk(). batch_size=2 red-line.
        Old generate_video_chunk() preserved as fallback.
        """
        import os, io, time, tempfile, copy
        import numpy as np
        import torch, cv2, soundfile as sf

        if container_fmt != "fmp4":
            raise ValueError(f"container_fmt={container_fmt!r} not supported in phase 1 (fmp4 only)")

        ref = self._load_reference(reference_state)
        if ref:
            self.sophie_frame_list_cycle = ref["frame_list_cycle"]
            self.sophie_coord_list_cycle = ref["coord_list_cycle"]
            self.sophie_input_latent_list_cycle = ref["input_latent_list_cycle"]
            print(f"[MuseTalk stream] reference_state={reference_state!r} loaded", flush=True)

        if not self.sophie_ready:
            yield {
                "seq": 0, "fmp4_bytes": b"", "frame_count": 0,
                "is_first": True, "is_last": True, "pts_offset_s": 0.0,
                "error": "sophie reference not cached",
            }
            return

        from musetalk.utils.utils import datagen

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        audio_arr, sr = sf.read(io.BytesIO(audio_pcm_bytes), dtype="float32")
        if sr != 16000:
            raise ValueError(f"Expected 16kHz PCM, got {sr}Hz")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav_f:
            tmp_wav = tmp_wav_f.name
        sf.write(tmp_wav, audio_arr, sr, subtype="PCM_16")
        print(f"[MuseTalk stream] wav dumped ({len(audio_arr)/sr:.2f}s . chunk_frames={chunk_frames})", flush=True)

        try:
            t0 = time.time()
            whisper_input_features, librosa_length = self.audio_processor.get_audio_feature(
                tmp_wav, weight_dtype=self.weight_dtype
            )
            whisper_chunks = self.audio_processor.get_whisper_chunk(
                whisper_input_features, device, self.weight_dtype, self.whisper, librosa_length,
                fps=fps, audio_padding_length_left=2, audio_padding_length_right=2,
            )
            video_num = len(whisper_chunks)
            total_chunks = int(np.ceil(video_num / chunk_frames))
            print(f"[MuseTalk stream] audio features: frames={video_num} chunks={total_chunks} feat_ms={(time.time()-t0)*1000:.0f}", flush=True)

            batch_size = 2
            gen = datagen(whisper_chunks=whisper_chunks,
                          vae_encode_latents=self.sophie_input_latent_list_cycle,
                          batch_size=batch_size, delay_frame=0, device=str(device))

            buffered = []
            seq = 0
            emitted_frames = 0

            t1 = time.time()
            for whisper_batch, latent_batch in gen:
                audio_feature_batch = self.pe(whisper_batch.to(device))
                latent_batch = latent_batch.to(device=device, dtype=self.unet.model.dtype)
                pred_latents = self.unet.model(latent_batch, self.timesteps,
                                               encoder_hidden_states=audio_feature_batch).sample
                pred_latents = pred_latents.to(device=device, dtype=self.vae.vae.dtype)
                recon = self.vae.decode_latents(pred_latents)
                for res_frame in recon:
                    buffered.append(res_frame)
                del pred_latents, recon, audio_feature_batch
                torch.cuda.empty_cache()

                while len(buffered) >= chunk_frames:
                    seg = buffered[:chunk_frames]
                    buffered = buffered[chunk_frames:]
                    seg_blended = self._blend_frames(seg, emitted_frames)
                    seg_audio = self._slice_audio(audio_arr, sr, seq, chunk_frames, fps)
                    seg_bytes = self._encode_fragment(
                        seg_blended, seg_audio, sr, fps, seq, emit_init=(seq == 0)
                    )
                    pts_offset = seq * (chunk_frames / fps)
                    is_last_now = (emitted_frames + len(seg_blended) >= video_num) and (len(buffered) == 0)
                    yield {
                        "seq": seq,
                        "fmp4_bytes": seg_bytes,
                        "frame_count": len(seg_blended),
                        "is_first": (seq == 0),
                        "is_last": is_last_now,
                        "pts_offset_s": pts_offset,
                    }
                    seq += 1
                    emitted_frames += len(seg_blended)

            if buffered:
                seg_blended = self._blend_frames(buffered, emitted_frames)
                seg_audio = self._slice_audio(audio_arr, sr, seq, chunk_frames, fps)
                seg_bytes = self._encode_fragment(
                    seg_blended, seg_audio, sr, fps, seq, emit_init=(seq == 0)
                )
                pts_offset = seq * (chunk_frames / fps)
                yield {
                    "seq": seq,
                    "fmp4_bytes": seg_bytes,
                    "frame_count": len(seg_blended),
                    "is_first": (seq == 0),
                    "is_last": True,
                    "pts_offset_s": pts_offset,
                }
                seq += 1
                emitted_frames += len(seg_blended)
                buffered = []

            print(f"[MuseTalk stream] DONE chunks={seq} frames={emitted_frames} unet+blend+mux_total={(time.time()-t1)*1000:.0f}ms e2e={(time.time()-t0):.2f}s", flush=True)
        finally:
            try:
                os.unlink(tmp_wav)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# FastAPI ASGI app
# ---------------------------------------------------------------------------


@app.function(
    image=musetalk_image,
    secrets=[MUSETALK_AUTH_TOKEN_SECRET],
    timeout=900,
)
@modal.asgi_app()
def fastapi_app():
    import os

    from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File, Form, Header
    from fastapi.responses import JSONResponse

    api = FastAPI(title="castle-voice-engine MuseTalk")
    runner = MuseTalkRunner()
    expected_token = os.environ.get("MUSETALK_AUTH_TOKEN", "")

    # Server-side defense-in-depth for Sally hard rule (Gate 4 WARN-1 補強).
    # Client (castle/integrations/musetalk_client.py) already enforces subject_guard;
    # this inline set is the last line of defense in case any caller bypasses the client.
    # Keep in sync with castle/safety/subject_guard.py _DENIED_SUBJECTS.
    _SERVER_DENIED_SUBJECTS = frozenset({
        "sally", "minor", "child", "stranger", "visitor",
    })

    def _check_auth(authorization: str | None) -> None:
        if not expected_token:
            return  # dev mode
        if authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="invalid bearer")

    @api.get("/musetalk/health")
    async def health(authorization: str | None = Header(None)):
        _check_auth(authorization)
        info = runner.warm.remote()
        return info

    @api.post("/musetalk/enroll")
    async def enroll(
        image: UploadFile = File(...),
        subject: str = Form("speaker_unknown"),
        authorization: str | None = Header(None),
    ):
        _check_auth(authorization)
        # Server-side Sally hard rule defense-in-depth (Gate 4 WARN-1).
        # Client already passed subject_guard; this catches any bypass.
        subj_lower = (subject or "").strip().lower()
        if subj_lower in _SERVER_DENIED_SUBJECTS or not subj_lower:
            raise HTTPException(
                status_code=403,
                detail=f"subject={subj_lower!r} blocked by server-side hard rule",
            )
        contents = await image.read()
        # Persist into the weights volume so MuseTalkRunner can pick it up next cold start
        out_path = f"/weights/assets/{subject}.png"
        os.makedirs("/weights/assets", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(contents)
        MUSETALK_VOLUME.commit()
        return JSONResponse({"ok": True, "stored": out_path, "subject": subject})

    @api.websocket("/musetalk/stream")
    async def stream(ws: WebSocket):
        # NOTE: Modal does not yet expose websocket auth headers on
        # ws.headers in all SDK versions; relying on init frame token.
        await ws.accept()
        try:
            init = await ws.receive_json()
            if expected_token and init.get("auth") != expected_token:
                await ws.close(code=4401, reason="invalid bearer")
                return

            fps = int(init.get("fps", 25))
            subject = init.get("subject", "speaker_unknown")
            print(f"[MuseTalk WS] init subject={subject} fps={fps}", flush=True)

            while True:
                audio_bytes = await ws.receive_bytes()
                result = await runner.generate_video_chunk.remote.aio(
                    audio_bytes, fps=fps
                )
                if result["video_bytes"]:
                    await ws.send_bytes(result["video_bytes"])
        except Exception as e:
            print(f"[MuseTalk WS] closed: {e}", flush=True)
            try:
                await ws.close(code=1011, reason=str(e)[:120])
            except Exception:
                pass

    return api
