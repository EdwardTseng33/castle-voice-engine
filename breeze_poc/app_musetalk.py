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

        # v0.10 Phase 1 multi-reference cache.
        self.refs = {}
        self.idle_ref_ids = []

        sophie_path = "/weights/assets/sophie-portrait-original.png"
        if os.path.exists(sophie_path):
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

                # Landmark + bbox (single image -> coord_list len 1, frame_list len 1)
                # MuseTalk v15: extra_margin=10 default
                coord_list, frame_list = get_landmark_and_bbox([sophie_path], 0)  # positional upperbondrange=0
                print(f"[MuseTalk] Sophie landmark+bbox extracted: coord_list={len(coord_list)} frame_list={len(frame_list)}", flush=True)
                if not coord_list or coord_list[0] == coord_placeholder:
                    print("[MuseTalk] WARN Sophie face detection returned placeholder bbox; skip latent cache", flush=True)
                else:
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

                    # Cycle so we always have a frame even when audio_chunk_count > 1
                    self.sophie_frame_list_cycle = frame_list + frame_list[::-1]
                    self.sophie_coord_list_cycle = new_coord_list + new_coord_list[::-1]
                    self.sophie_input_latent_list_cycle = input_latent_list + input_latent_list[::-1]
                    self.sophie_ready = True
                    print(f"[MuseTalk] Sophie reference ready (latents={len(input_latent_list)}, cycle={len(self.sophie_frame_list_cycle)})", flush=True)
            except Exception as e:
                import traceback
                print(f"[MuseTalk] Sophie precompute FAILED: {type(e).__name__}: {e}", flush=True)
                print(traceback.format_exc(), flush=True)
                # Do not crash cold start; health endpoint will report sophie_reference_cached=False
        else:
            print(f"[MuseTalk] Sophie portrait not found at {sophie_path}; precompute skipped", flush=True)

        # v0.10 Phase 1: load multi-reference library.
        self._load_reference_library()

        elapsed = round(time.time() - t0, 1)
        print(f"[MuseTalk] ready in {elapsed}s (sophie_ready={self.sophie_ready}, refs={list(self.refs.keys())})", flush=True)

    def _build_reference_cycles(self, video_path):
        import os, cv2, tempfile
        from musetalk.utils.preprocessing import get_landmark_and_bbox, coord_placeholder
        if not os.path.exists(video_path):
            return None
        cap = cv2.VideoCapture(video_path)
        frames = []
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            frames.append(fr)
        cap.release()
        if not frames:
            print(f"[MuseTalk ref] {video_path}: 0 frames", flush=True)
            return None
        tmp_dir = tempfile.mkdtemp(prefix="musetalk_ref_")
        paths = []
        for i, fr in enumerate(frames):
            fp = f"{tmp_dir}/{i:05d}.png"
            cv2.imwrite(fp, fr)
            paths.append(fp)
        try:
            coord_list, frame_list = get_landmark_and_bbox(paths, 0)
        except Exception as e:
            print(f"[MuseTalk ref] {video_path}: landmark fail {type(e).__name__}: {e}", flush=True)
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
        if not input_latent_list:
            return None
        frame_cycle = frame_list + frame_list[::-1]
        coord_cycle = new_coord_list + new_coord_list[::-1]
        latent_cycle = input_latent_list + input_latent_list[::-1]
        return coord_cycle, frame_cycle, latent_cycle

    def _load_reference_library(self):
        import os, time
        ref_dir = "/weights/assets/references"
        if not os.path.isdir(ref_dir):
            print(f"[MuseTalk ref] {ref_dir} missing", flush=True)
            return
        wanted = ["idle.mp4", "idle-2.mp4", "idle-3.mp4", "idle-4.mp4", "speaking.mp4"]
        for name in wanted:
            path = os.path.join(ref_dir, name)
            ref_id = name.removesuffix(".mp4")
            t0 = time.time()
            built = self._build_reference_cycles(path)
            if built is None:
                print(f"[MuseTalk ref] SKIP {ref_id}", flush=True)
                continue
            coord_cycle, frame_cycle, latent_cycle = built
            self.refs[ref_id] = {"coord_cycle": coord_cycle, "frame_cycle": frame_cycle, "latent_cycle": latent_cycle}
            if ref_id.startswith("idle"):
                self.idle_ref_ids.append(ref_id)
            print(f"[MuseTalk ref] {ref_id}: cycle_len={len(frame_cycle)} ({(time.time()-t0)*1000:.0f}ms)", flush=True)

    @modal.method()
    def warm(self):
        return {
            "status": "ready",
            "model": "MuseTalk v1.5",
            "license": "MIT (Lyra Lab/Tencent Music Entertainment)",
            "sophie_reference_cached": self.sophie_ready,
            "refs_loaded": list(self.refs.keys()),
            "idle_ref_count": len(self.idle_ref_ids),
        }

    @modal.method()
    def generate_video_chunk(self, audio_pcm_bytes: bytes, fps: int = 25):
        # Phase 7a (2026-05-23 calcifer): full pipeline ported from scripts/inference.py.
        # PCM bytes -> wav -> get_audio_feature -> whisper_chunks -> datagen -> unet+vae -> blend -> ffmpeg mp4.
        import os, io, time, tempfile, subprocess, copy
        import numpy as np
        import torch, cv2, soundfile as sf
        from tqdm import tqdm

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
            cmd_v = ["ffmpeg","-y","-v","warning","-r",str(fps),"-f","image2",
                     "-i",f"{tmp_frames_dir}/%08d.png","-vcodec","libx264",
                     "-vf","format=yuv420p","-crf","18",tmp_silent]
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


    # -------------------------------------------------------------------------
    # v0.10 Phase 1 (2026-05-25 calcifer): continuous frame generators
    # -------------------------------------------------------------------------
    @modal.method()
    def list_references(self):
        return {rid: len(self.refs[rid]["frame_cycle"]) for rid in self.refs}

    @modal.method()
    def generate_idle_continuous(self, duration_s: float = 30.0, fps: int = 25,
                                  start_ref=None, rotate_every_s=None):
        import time, cv2
        if not self.idle_ref_ids:
            yield {"frame": b"", "error": "no idle references loaded"}
            return
        target_count = int(duration_s * fps)
        if start_ref and start_ref in self.idle_ref_ids:
            ref_idx = self.idle_ref_ids.index(start_ref)
        else:
            ref_idx = 0
        t0 = time.time()
        emitted = 0
        ref_cycle_pos = 0
        last_rotate_t = t0
        while emitted < target_count:
            cur_ref = self.idle_ref_ids[ref_idx]
            frame_cycle = self.refs[cur_ref]["frame_cycle"]
            frame = frame_cycle[ref_cycle_pos % len(frame_cycle)]
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                yield {"frame": b"", "error": f"jpeg encode fail at emit={emitted}"}
                return
            yield {"frame": jpg.tobytes(), "ref_id": cur_ref, "emit_index": emitted, "mode": "idle"}
            emitted += 1
            ref_cycle_pos += 1
            now = time.time()
            wrap = (ref_cycle_pos % len(frame_cycle) == 0)
            time_rotate = (rotate_every_s is not None and (now - last_rotate_t) >= rotate_every_s)
            if wrap or time_rotate:
                ref_idx = (ref_idx + 1) % len(self.idle_ref_ids)
                ref_cycle_pos = 0
                last_rotate_t = now
    @modal.method()
    def generate_speaking_continuous(self, audio_pcm_bytes: bytes, fps: int = 25, ref_id: str = "speaking"):
        import io, time, tempfile, os, copy, cv2, numpy as np, torch
        import soundfile as sf
        from musetalk.utils.utils import datagen
        from musetalk.utils.blending import get_image
        if ref_id not in self.refs:
            fallback = self.idle_ref_ids[0] if self.idle_ref_ids else None
            if fallback is None:
                yield {"frame": b"", "error": f"ref {ref_id!r} not loaded and no idle fallback"}
                return
            print(f"[MuseTalk speak] ref {ref_id!r} missing; fallback {fallback!r}", flush=True)
            ref_id = fallback
        ref = self.refs[ref_id]
        coord_cycle = ref["coord_cycle"]
        frame_cycle = ref["frame_cycle"]
        latent_cycle = ref["latent_cycle"]
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        audio_arr, sr = sf.read(io.BytesIO(audio_pcm_bytes), dtype="float32")
        if sr != 16000:
            yield {"frame": b"", "error": f"expected 16kHz PCM, got {sr}Hz"}
            return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav_f:
            tmp_wav = tmp_wav_f.name
        sf.write(tmp_wav, audio_arr, sr, subtype="PCM_16")
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
            print(f"[MuseTalk speak] audio_chunks={video_num} ref={ref_id} ({(time.time()-t0)*1000:.0f}ms)", flush=True)
            batch_size = 2
            gen = datagen(whisper_chunks=whisper_chunks, vae_encode_latents=latent_cycle,
                          batch_size=batch_size, delay_frame=0, device=str(device))
            emitted = 0
            t1 = time.time()
            for i, (whisper_batch, latent_batch) in enumerate(gen):
                audio_feature_batch = self.pe(whisper_batch.to(device))
                latent_batch = latent_batch.to(device=device, dtype=self.unet.model.dtype)
                pred_latents = self.unet.model(latent_batch, self.timesteps,
                                                encoder_hidden_states=audio_feature_batch).sample
                pred_latents = pred_latents.to(device=device, dtype=self.vae.vae.dtype)
                recon = self.vae.decode_latents(pred_latents)
                for res_frame in recon:
                    bbox = coord_cycle[emitted % len(coord_cycle)]
                    ori_frame = copy.deepcopy(frame_cycle[emitted % len(frame_cycle)])
                    x1, y1, x2, y2 = bbox
                    try:
                        res_frame_resized = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
                    except Exception:
                        emitted += 1
                        continue
                    combine_frame = get_image(ori_frame, res_frame_resized, [x1, y1, x2, y2],
                                              mode="jaw", fp=self.fp)
                    ok, jpg = cv2.imencode(".jpg", combine_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if not ok:
                        emitted += 1
                        continue
                    yield {"frame": jpg.tobytes(), "ref_id": ref_id, "emit_index": emitted, "mode": "speaking"}
                    emitted += 1
                del pred_latents, recon, audio_feature_batch
                torch.cuda.empty_cache()
            print(f"[MuseTalk speak] emitted={emitted} dt={(time.time()-t1)*1000:.0f}ms", flush=True)
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

    from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File, Form, Header, Request
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

    # -------------------------------------------------------------------------
    # v0.10 Phase 1 continuous endpoints (calcifer 2026-05-25)
    # -------------------------------------------------------------------------
    BOUNDARY = "musetalk-frame-boundary"

    def _multipart_frame(jpg_bytes: bytes) -> bytes:
        header = f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpg_bytes)}\r\n\r\n"
        return header.encode("ascii") + jpg_bytes + b"\r\n"

    @api.get("/musetalk/references")
    async def references(authorization: str | None = Header(None)):
        _check_auth(authorization)
        return runner.list_references.remote()

    @api.get("/musetalk/idle_continuous")
    async def idle_continuous(
        duration_s: float = 30.0,
        fps: int = 25,
        start_ref: str | None = None,
        rotate_every_s: float | None = None,
        authorization: str | None = Header(None),
    ):
        _check_auth(authorization)
        from fastapi.responses import StreamingResponse

        def gen():
            for item in runner.generate_idle_continuous.remote_gen(
                duration_s=duration_s, fps=fps, start_ref=start_ref,
                rotate_every_s=rotate_every_s,
            ):
                if item.get("error"):
                    err = item["error"].encode("utf-8")
                    yield (f"--{BOUNDARY}\r\nContent-Type: text/plain\r\nContent-Length: {len(err)}\r\n\r\n").encode("ascii") + err + b"\r\n"
                    return
                yield _multipart_frame(item["frame"])
            yield f"--{BOUNDARY}--\r\n".encode("ascii")

        return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}")

    @api.post("/musetalk/speaking_continuous")
    async def speaking_continuous(
        request: Request,
        fps: int = 25,
        ref_id: str = "speaking",
        authorization: str | None = Header(None),
    ):
        _check_auth(authorization)
        from fastapi.responses import StreamingResponse
        audio_bytes = await request.body()
        if not audio_bytes:
            return JSONResponse({"error": "empty body; expected 16kHz mono PCM-16 wav"}, status_code=400)

        def gen():
            for item in runner.generate_speaking_continuous.remote_gen(
                audio_bytes, fps=fps, ref_id=ref_id,
            ):
                if item.get("error"):
                    err = item["error"].encode("utf-8")
                    yield (f"--{BOUNDARY}\r\nContent-Type: text/plain\r\nContent-Length: {len(err)}\r\n\r\n").encode("ascii") + err + b"\r\n"
                    return
                yield _multipart_frame(item["frame"])
            yield f"--{BOUNDARY}--\r\n".encode("ascii")

        return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}")
    return api
