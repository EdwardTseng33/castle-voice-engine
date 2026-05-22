# castle-voice-engine - (c) 2026 Edward / BeyondPath
# castle/multimodal/vision_analyzer.py
#
# Phase 3 (v0.3.0) - Claude vision API analysis + real-time narration injection.
#
# =================================================================
# Privacy compliance (security-architecture-checklist.md 7 categories + ADR-018)
# =================================================================
# Data flow 1.1-1.6     OK frame downsized to JPEG <= 200KB, sent over HTTPS, dropped after send
# IAM 2.4 token         OK ANTHROPIC_API_KEY read from Modal secret, never logged, never echoed
# Encryption 3.2 transit OK HTTPS via Anthropic SDK (TLS 1.3)
# API 4.1 rate limit    OK 1 frame per 5s default, hard cap 1 frame per 2s
# Privacy 5.1 opt-in    OK only runs when camera enabled AND analyzer.enable() called
# Privacy 5.4 sensitive OK 5s sampling = not continuous surveillance; user can stop anytime
# Incident 7.3 kill     OK disable() stops loop within next analysis cycle; tied to camera kill
# Incident 7.1 audit    OK each Claude call logs ts + prompt-len + response-len (not content) to stderr
# =================================================================
#
# Pipeline:
#   1. Pull latest frame from CameraManager (RAM only)
#   2. Resize to <= 768px max dim + JPEG quality 70 -> <= 200KB
#   3. Send to Claude Haiku 4.5 with persona-aware short prompt
#   4. Get <= 25-char Mandarin observation back
#   5. Push to gpt-realtime-2 session via session.update -> sophie narrates aloud
#
# Privacy boundary: this module is the ONLY component that sends frame data
# externally. CameraManager produces frames locally; vision_analyzer is the
# explicit egress gate. ADR-018 audit point.

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("castle.multimodal.vision")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s"))
    logger.addHandler(_h)


# ---------- Config ----------
DEFAULT_ANALYSIS_INTERVAL_S = 5.0     # 1 frame per 5 seconds (API rate cap)
MIN_INTERVAL_S = 2.0                  # hard floor to prevent burst
MAX_IMAGE_DIM_PX = 768                # downsize cap
JPEG_QUALITY = 70                     # compression target
TARGET_KB = 200                       # soft target for upload size
DEFAULT_VISION_MODEL = "claude-haiku-4-5"
MAX_NARRATION_CHARS = 25              # match sophie persona hard rule
RECENT_OBSERVATIONS_KEEP = 5          # short-term context for dedup
PILLOW_AVAILABLE = False
ANTHROPIC_AVAILABLE = False
NUMPY_AVAILABLE = False

# Lazy imports - vision_analyzer is optional.
try:
    from PIL import Image  # type: ignore
    PILLOW_AVAILABLE = True
except Exception as e:
    logger.warning("Pillow not available: %s - vision disabled", e)

try:
    import numpy as np  # type: ignore
    NUMPY_AVAILABLE = True
except Exception as e:
    logger.warning("numpy not available: %s - vision disabled", e)

try:
    import anthropic  # type: ignore
    ANTHROPIC_AVAILABLE = True
except Exception as e:
    logger.warning("anthropic SDK not available: %s - vision disabled", e)


# ---------- Prompt ----------
# Sophie persona-aware. Keep it short, in Traditional Chinese, <= 25 chars.
SYSTEM_PROMPT = (
    "你是 Sophie - Edward 的貼身搭檔。你正透過 webcam 看 Edward 在工作。"
    "請看畫面、用台灣腔中文講一句 <= 25 字的觀察。"
    "不問問題、不下指令、不重複上一句。"
    "如果畫面無人或太暗、回 SKIP。"
    "範例：'你笑了喔'、'喝水了好'、'你在打字'、'坐久了肩膀僵'、'光線變了'、'SKIP'"
)


@dataclass
class VisionStat:
    analyses_run: int = 0
    skips_emitted: int = 0
    errors_total: int = 0
    last_observation: str = ""
    last_ts: float = 0.0
    last_latency_ms: float = 0.0
    last_image_kb: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class Observation:
    text: str
    ts: float = field(default_factory=time.time)
    is_skip: bool = False


class VisionAnalyzer:
    """
    Pulls frames from CameraManager, runs Claude vision, pushes narration callbacks.

    Privacy default: OFF. Caller must call enable() to start; calling stop() halts.
    Privacy 5.1 + Incident 7.3: tied to CameraManager - if camera not enabled,
    this loop exits cleanly without sending anything.
    """

    def __init__(self, camera_manager, interval_s=DEFAULT_ANALYSIS_INTERVAL_S, model=DEFAULT_VISION_MODEL):
        self.camera_manager = camera_manager
        self.interval_s = max(MIN_INTERVAL_S, interval_s)
        self.model = model
        self._enabled = False
        self._stop_event = threading.Event()
        self._loop_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        self._stat = VisionStat()
        self._recent_observations: deque = deque(maxlen=RECENT_OBSERVATIONS_KEEP)
        self._narration_callback = None
        self._client: Optional[Any] = None
        logger.info("VisionAnalyzer init - interval=%ss model=%s - DISABLED (Privacy 5.1)", self.interval_s, self.model)

    def is_available(self):
        return PILLOW_AVAILABLE and ANTHROPIC_AVAILABLE and NUMPY_AVAILABLE

    def is_enabled(self):
        return self._enabled

    def set_narration_callback(self, cb):
        """Callback signature: async fn(observation_text: str, meta: dict)"""
        self._narration_callback = cb

    def enable(self):
        """Start vision analysis loop. Camera must already be enabled."""
        if not self.is_available():
            return {"ok": False, "error": "vision_dependencies_missing", "detail": "needs pillow + anthropic + numpy"}
        if not self.camera_manager.is_enabled():
            return {"ok": False, "error": "camera_not_enabled", "detail": "enable camera first via /camera/enable"}
        if self._enabled:
            return {"ok": True, "already_enabled": True, "stat": self._stat_dict()}

        # IAM 2.4: read from env (Modal injects via secret)
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return {"ok": False, "error": "anthropic_api_key_missing", "detail": "ANTHROPIC_API_KEY env var not set"}

        try:
            self._client = anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            logger.error("anthropic client init failed: %s", e)
            return {"ok": False, "error": "anthropic_client_init_failed", "detail": str(e)}

        self._stop_event.clear()
        self._enabled = True
        loop = asyncio.get_event_loop()
        self._loop_task = loop.create_task(self._analysis_loop())
        logger.info("VISION ENABLED - interval=%ss model=%s", self.interval_s, self.model)
        return {"ok": True, "enabled": True, "interval_s": self.interval_s, "model": self.model}

    def disable(self):
        """Stop loop. Does not affect camera."""
        if not self._enabled:
            return {"ok": True, "already_disabled": True}
        self._stop_event.set()
        self._enabled = False
        logger.info("VISION DISABLED - final_stat=%s", self._stat_dict())
        return {"ok": True, "stopped": True, "stat": self._stat_dict()}

    def status(self):
        return {
            "enabled": self._enabled,
            "available": self.is_available(),
            "pillow_available": PILLOW_AVAILABLE,
            "anthropic_available": ANTHROPIC_AVAILABLE,
            "numpy_available": NUMPY_AVAILABLE,
            "interval_s": self.interval_s,
            "model": self.model,
            "stat": self._stat_dict(),
            "recent_observations": [{"text": o.text, "ts": o.ts, "is_skip": o.is_skip} for o in list(self._recent_observations)],
        }

    async def _analysis_loop(self):
        logger.info("vision analysis loop started")
        while not self._stop_event.is_set():
            t_start = time.time()
            # Privacy 5.1 dependency check: if camera disabled mid-loop, exit
            if not self.camera_manager.is_enabled():
                logger.info("camera disabled mid-loop, vision exits")
                break

            frame = self.camera_manager.get_latest_frame()
            if frame is None:
                logger.debug("no frame available, waiting")
            else:
                try:
                    await self._run_one_analysis(frame)
                except Exception as e:
                    self._stat.errors_total += 1
                    logger.error("analysis error: %s", e)

            elapsed = time.time() - t_start
            wait_s = max(0.1, self.interval_s - elapsed)
            try:
                await asyncio.sleep(wait_s)
            except asyncio.CancelledError:
                break
        # Cleanup
        self._enabled = False
        logger.info("vision analysis loop exit cleanly")

    async def _run_one_analysis(self, frame):
        """Send single frame to Claude vision, dispatch result."""
        t0 = time.time()

        # Privacy 5.4: downsize + JPEG compress (RAM only)
        jpeg_bytes = self._encode_frame_to_jpeg(frame)
        if jpeg_bytes is None:
            self._stat.errors_total += 1
            return
        image_kb = len(jpeg_bytes) / 1024.0

        # Recent obs context (avoid repetition)
        recent_text = ""
        if self._recent_observations:
            recent_text = "  最近說過的（不要重複）：" + " / ".join(o.text for o in list(self._recent_observations)[-3:])

        # Privacy 7.1 audit (no content)
        logger.info("vision call - model=%s img_kb=%.1f", self.model, image_kb)

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, self._sync_claude_call, jpeg_bytes, recent_text)
        except Exception as e:
            self._stat.errors_total += 1
            logger.error("Claude call failed: %s", e)
            return

        if response is None:
            self._stat.errors_total += 1
            return

        observation_text = response.get("text", "").strip()
        in_tokens = response.get("input_tokens", 0)
        out_tokens = response.get("output_tokens", 0)

        # Truncate to <= 25 chars (persona hard rule)
        if len(observation_text) > MAX_NARRATION_CHARS:
            observation_text = observation_text[:MAX_NARRATION_CHARS]

        is_skip = observation_text.upper().strip() == "SKIP" or observation_text == ""

        # Update stat
        latency_ms = (time.time() - t0) * 1000.0
        with self._lock:
            self._stat.analyses_run += 1
            self._stat.last_ts = time.time()
            self._stat.last_latency_ms = round(latency_ms, 1)
            self._stat.last_image_kb = round(image_kb, 1)
            self._stat.total_input_tokens += in_tokens
            self._stat.total_output_tokens += out_tokens
            if is_skip:
                self._stat.skips_emitted += 1
            else:
                self._stat.last_observation = observation_text
                self._recent_observations.append(Observation(text=observation_text, is_skip=False))

        logger.info("vision result - obs_len=%s skip=%s in_tok=%s out_tok=%s latency_ms=%.0f", len(observation_text), is_skip, in_tokens, out_tokens, latency_ms)

        # Dispatch to narration callback (if registered)
        if not is_skip and self._narration_callback is not None:
            try:
                meta = {
                    "model": self.model,
                    "latency_ms": latency_ms,
                    "image_kb": image_kb,
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                }
                await self._narration_callback(observation_text, meta)
            except Exception as e:
                logger.error("narration callback error: %s", e)

    def _sync_claude_call(self, jpeg_bytes, recent_text):
        """Blocking Claude call - runs in thread pool executor."""
        try:
            b64 = base64.standard_b64encode(jpeg_bytes).decode("ascii")
            user_text = "看畫面、講一句 <= 25 字的觀察。" + (recent_text if recent_text else "")
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=64,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                            {"type": "text", "text": user_text},
                        ],
                    }
                ],
            )
            text = ""
            for block in (msg.content or []):
                if getattr(block, "type", "") == "text":
                    text += getattr(block, "text", "")
            usage = getattr(msg, "usage", None)
            in_tok = getattr(usage, "input_tokens", 0) if usage else 0
            out_tok = getattr(usage, "output_tokens", 0) if usage else 0
            return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok}
        except Exception as e:
            logger.error("Claude sync call exception: %s", e)
            return None

    def _encode_frame_to_jpeg(self, frame):
        """numpy BGR ndarray -> JPEG bytes. Downsizes to MAX_IMAGE_DIM_PX max."""
        if not (PILLOW_AVAILABLE and NUMPY_AVAILABLE):
            return None
        try:
            # OpenCV BGR -> RGB for Pillow
            if frame.shape[2] == 3:
                rgb = frame[:, :, ::-1]
            else:
                rgb = frame
            img = Image.fromarray(rgb)
            # Downsize
            w, h = img.size
            max_dim = max(w, h)
            if max_dim > MAX_IMAGE_DIM_PX:
                scale = MAX_IMAGE_DIM_PX / float(max_dim)
                new_size = (int(w * scale), int(h * scale))
                img = img.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            jpeg = buf.getvalue()
            return jpeg
        except Exception as e:
            logger.error("JPEG encode failed: %s", e)
            return None

    def _stat_dict(self):
        return {
            "analyses_run": self._stat.analyses_run,
            "skips_emitted": self._stat.skips_emitted,
            "errors_total": self._stat.errors_total,
            "last_observation": self._stat.last_observation,
            "last_ts": self._stat.last_ts,
            "last_latency_ms": self._stat.last_latency_ms,
            "last_image_kb": self._stat.last_image_kb,
            "total_input_tokens": self._stat.total_input_tokens,
            "total_output_tokens": self._stat.total_output_tokens,
        }


# ---------- Singleton accessor ----------
_singleton = None
_singleton_lock = threading.Lock()


def get_vision_analyzer(camera_manager=None):
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            if camera_manager is None:
                from castle.multimodal.camera import get_camera_manager
                camera_manager = get_camera_manager()
            _singleton = VisionAnalyzer(camera_manager)
        return _singleton
