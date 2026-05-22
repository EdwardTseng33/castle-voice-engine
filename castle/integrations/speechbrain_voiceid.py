# castle-voice-engine - castle/integrations/speechbrain_voiceid.py
# (c) 2026 Edward / BeyondPath
#
# SpeechBrain ECAPA-TDNN 聲紋認證 (Picovoice Eagle 開源替代)
# Voice Path v2.0 Phase 2 後半段 · 2026-05-22 蘇菲 ship
#
# 為什麼換掉 Picovoice Eagle:
#   - Picovoice 2026 改純企業導向 (公司 email · 7 天試用)、個人版退場
#   - SpeechBrain 是 Mila (Université de Montréal) 主導開源 PyTorch toolkit
#     · Apache-2.0 license · GitHub 4.4k stars · 業界 SOTA speaker verification
#   - ECAPA-TDNN 預訓練模型在 VoxCeleb 訓練、CPU 可跑 (~80MB model)
#
# 隱私守則 (對應 security-architecture-checklist.md + ADR-018):
#   - 1.1-1.6 資料流: 聲紋 embedding (1x192 float vector) 本機算、不上雲
#   - 5.4 不主動收集敏感資料: enrolled embedding 存 .npy 本機檔
#   - 6.4 第三方信任: SpeechBrain Mila lab · Apache-2.0 · 學術背書
#   - 6.7 license: Apache-2.0 (商用 OK · 跟 ADR-018 MediaPipe 同 tier)
#
# 用法 (Edward 不必動、蘇菲 / 卡西法跑):
#   from castle.integrations.speechbrain_voiceid import (
#       enroll_speaker, verify_speaker, is_speechbrain_ready
#   )
#
#   # 1. enrollment (一次性、用 Edward 4/28 錄音)
#   enroll_speaker("voice_samples/edward_for_eagle.m4a")
#
#   # 2. verification (即時、來自麥克風 chunk)
#   match, score = verify_speaker(audio_chunk_path)
#   if match: print("是 Edward")
#
# SDK lazy import: speechbrain / torch / torchaudio 沒裝也不炸 castle/ 其他段。

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# SpeechBrain + Torch lazy import (重 dep · 不該整個 castle/ 都連帶炸)
_sb_recognizer = None
_torch = None
_torchaudio = None


def _lazy_import_speechbrain():
    """Lazy-load SpeechBrain SpeakerRecognition (含 ECAPA-TDNN 預訓練 model)."""
    global _sb_recognizer, _torch, _torchaudio
    if _sb_recognizer is not None:
        return _sb_recognizer
    try:
        import torch  # type: ignore
        import torchaudio  # type: ignore
        from speechbrain.inference.speaker import SpeakerRecognition  # type: ignore
    except ImportError as e:
        logger.info("speechbrain / torch 未安裝 (%s)、voice ID OFF", str(e)[:80])
        return None

    _torch = torch
    _torchaudio = torchaudio

    base_dir = Path(__file__).resolve().parent.parent.parent
    cache_dir = base_dir / "pretrained_models" / "spkrec-ecapa-voxceleb"

    # Windows symlink 權限問題避開 (HF Hub default symlink 需要 admin / Dev Mode)
    # SpeechBrain 1.0+ LocalStrategy enum 改 COPY (不是字串、是 enum)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    # 嘗試 import LocalStrategy enum (SpeechBrain 1.0+)
    local_strategy = None
    try:
        from speechbrain.utils.fetching import LocalStrategy  # type: ignore
        local_strategy = LocalStrategy.COPY
    except (ImportError, AttributeError):
        # SpeechBrain < 1.0 沒這 enum · fall back
        pass

    try:
        kwargs = {
            "source": "speechbrain/spkrec-ecapa-voxceleb",
            "savedir": str(cache_dir),
            "run_opts": {"device": "cpu"},
        }
        if local_strategy is not None:
            kwargs["local_strategy"] = local_strategy
        _sb_recognizer = SpeakerRecognition.from_hparams(**kwargs)
        return _sb_recognizer
    except Exception as e:  # noqa: BLE001
        logger.warning("SpeechBrain load 失敗 (%s)、voice ID OFF", str(e)[:200])
        return None


@dataclass
class SpeechBrainConfig:
    enrolled_embedding_path: str = "voice_samples/edward_embedding.npy"
    voice_sample_path: str = "voice_samples/edward_for_eagle.m4a"  # Edward 4/28 自錄
    similarity_threshold: float = 0.25  # ECAPA-TDNN cosine threshold (業界推薦 0.2-0.3)

    @classmethod
    def from_env(cls) -> "SpeechBrainConfig":
        return cls(
            enrolled_embedding_path=os.environ.get(
                "VOICEID_ENROLLED_EMBEDDING",
                "voice_samples/edward_embedding.npy",
            ).strip(),
            voice_sample_path=os.environ.get(
                "VOICEID_VOICE_SAMPLE",
                "voice_samples/edward_for_eagle.m4a",
            ).strip(),
            similarity_threshold=float(os.environ.get("VOICEID_THRESHOLD", "0.25")),
        )


def is_speechbrain_ready(cfg: Optional[SpeechBrainConfig] = None) -> dict[str, bool]:
    """檢查 SpeechBrain 安裝 + enrollment 狀態."""
    if cfg is None:
        cfg = SpeechBrainConfig.from_env()

    base_dir = Path(__file__).resolve().parent.parent.parent

    def _abs(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else base_dir / path

    try:
        import torch  # noqa: F401
        torch_installed = True
    except ImportError:
        torch_installed = False

    try:
        import speechbrain  # noqa: F401
        sb_installed = True
    except ImportError:
        sb_installed = False

    return {
        "torch_installed": torch_installed,
        "speechbrain_installed": sb_installed,
        "voice_sample_exists": _abs(cfg.voice_sample_path).exists(),
        "enrolled_embedding_exists": _abs(cfg.enrolled_embedding_path).exists(),
        "model_cached": (base_dir / "pretrained_models" / "spkrec-ecapa-voxceleb").exists(),
    }


def _load_audio_to_tensor(audio_path: Path):
    """
    讀音檔轉成 16kHz mono torch tensor (SpeechBrain ECAPA expects 16kHz).

    繞過 torchaudio.load (新版 強制要 torchcodec + system ffmpeg)、
    改用 imageio-ffmpeg 轉 wav + soundfile 讀 numpy + 手動 → torch tensor.

    支援格式: 任何 ffmpeg 認得的 (m4a / mp3 / wav / flac / ogg / opus ...)
    """
    if _torch is None:
        raise RuntimeError("torch not loaded · _lazy_import_speechbrain() 失敗")

    try:
        import soundfile as sf  # type: ignore
        import numpy as np
    except ImportError as e:
        raise RuntimeError(
            f"soundfile / numpy 未安裝 · 跑 `pip install soundfile numpy` ({e})"
        )

    try:
        from imageio_ffmpeg import get_ffmpeg_exe  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            f"音檔解碼需 ffmpeg · 跑 `pip install imageio-ffmpeg` ({e})"
        )

    import subprocess
    import tempfile

    # 一律走 ffmpeg → 16kHz mono wav 暫存 (避開 torchaudio.load + torchcodec)
    ffmpeg = get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", str(audio_path),
                "-ac", "1",         # mono
                "-ar", "16000",     # 16 kHz
                "-acodec", "pcm_s16le",
                "-f", "wav",
                tmp_path,
            ],
            check=True,
            capture_output=True,
        )
        data, sample_rate = sf.read(tmp_path, dtype="float32", always_2d=False)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # numpy → torch tensor · shape (1, samples) 給 SpeechBrain encode_batch
    if data.ndim > 1:
        # safety net (ffmpeg 已 force ac=1、應該不會走到)
        data = data.mean(axis=1)
    signal = _torch.from_numpy(data).unsqueeze(0)
    return signal


def enroll_speaker(
    audio_path: str,
    cfg: Optional[SpeechBrainConfig] = None,
) -> dict[str, object]:
    """
    註冊 speaker · 抽 embedding 存 .npy.

    Args:
        audio_path: 聲音樣本路徑 (m4a / wav / mp3 都吃、torchaudio 自動轉)
        cfg: SpeechBrainConfig

    Returns:
        {
            "ok": bool,
            "embedding_path": str,
            "embedding_shape": tuple,
            "sample_duration_sec": float,
            "error": str | None,
        }
    """
    if cfg is None:
        cfg = SpeechBrainConfig.from_env()

    recognizer = _lazy_import_speechbrain()
    if recognizer is None:
        return {
            "ok": False,
            "embedding_path": "",
            "embedding_shape": (),
            "sample_duration_sec": 0.0,
            "error": "speechbrain 未安裝 · 跑: pip install speechbrain torch torchaudio",
        }

    base_dir = Path(__file__).resolve().parent.parent.parent

    def _abs(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else base_dir / path

    audio_full = _abs(audio_path)
    if not audio_full.exists():
        return {
            "ok": False,
            "embedding_path": "",
            "embedding_shape": (),
            "sample_duration_sec": 0.0,
            "error": f"音檔不存在: {audio_full}",
        }

    try:
        signal = _load_audio_to_tensor(audio_full)
        duration_sec = signal.shape[-1] / 16000.0

        # ECAPA-TDNN 抽 embedding (1x192)
        embeddings = recognizer.encode_batch(signal)
        # embeddings shape: (1, 1, 192) · squeeze 中間 dim
        emb_np = embeddings.squeeze(0).squeeze(0).cpu().numpy()

        # 存 .npy
        import numpy as np
        out_path = _abs(cfg.enrolled_embedding_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(out_path), emb_np)

        return {
            "ok": True,
            "embedding_path": str(out_path),
            "embedding_shape": tuple(emb_np.shape),
            "sample_duration_sec": float(duration_sec),
            "error": None,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "embedding_path": "",
            "embedding_shape": (),
            "sample_duration_sec": 0.0,
            "error": f"enroll 失敗: {str(e)[:200]}",
        }


def verify_speaker(
    audio_path: str,
    cfg: Optional[SpeechBrainConfig] = None,
) -> dict[str, object]:
    """
    驗證 audio 是不是 enrolled speaker.

    Args:
        audio_path: 待驗證的音檔
        cfg: SpeechBrainConfig (含 threshold)

    Returns:
        {
            "ok": bool,
            "match": bool,         # 是不是 enrolled speaker
            "similarity": float,   # cosine similarity 0-1
            "threshold": float,
            "error": str | None,
        }
    """
    if cfg is None:
        cfg = SpeechBrainConfig.from_env()

    recognizer = _lazy_import_speechbrain()
    if recognizer is None:
        return {
            "ok": False,
            "match": False,
            "similarity": 0.0,
            "threshold": cfg.similarity_threshold,
            "error": "speechbrain 未安裝",
        }

    base_dir = Path(__file__).resolve().parent.parent.parent

    def _abs(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else base_dir / path

    emb_path = _abs(cfg.enrolled_embedding_path)
    if not emb_path.exists():
        return {
            "ok": False,
            "match": False,
            "similarity": 0.0,
            "threshold": cfg.similarity_threshold,
            "error": f"沒 enrollment 紀錄 ({emb_path})、先跑 enroll_speaker()",
        }

    audio_full = _abs(audio_path)
    if not audio_full.exists():
        return {
            "ok": False,
            "match": False,
            "similarity": 0.0,
            "threshold": cfg.similarity_threshold,
            "error": f"音檔不存在: {audio_full}",
        }

    try:
        import numpy as np
        enrolled = np.load(str(emb_path))

        signal = _load_audio_to_tensor(audio_full)
        new_emb = recognizer.encode_batch(signal).squeeze(0).squeeze(0).cpu().numpy()

        # cosine similarity
        sim = float(
            np.dot(enrolled, new_emb)
            / (np.linalg.norm(enrolled) * np.linalg.norm(new_emb) + 1e-9)
        )

        return {
            "ok": True,
            "match": sim >= cfg.similarity_threshold,
            "similarity": sim,
            "threshold": cfg.similarity_threshold,
            "error": None,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "match": False,
            "similarity": 0.0,
            "threshold": cfg.similarity_threshold,
            "error": f"verify 失敗: {str(e)[:200]}",
        }
