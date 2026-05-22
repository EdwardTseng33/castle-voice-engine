# castle-voice-engine - (c) 2026 Edward / BeyondPath
# castle/multimodal/camera.py
#
# Phase 3 (v0.3.0) - Webcam frame grabber + MediaPipe landmark inference.
#
# =================================================================
# Privacy compliance (security-architecture-checklist.md 7 categories + ADR-018 3 tests)
# =================================================================
# Data flow 1.1-1.6     OK frame in-memory only, ndarray dropped after use, no disk write
# IAM 2.4 token         OK module does not touch tokens (Anthropic key handled in vision_analyzer)
# Encryption 3.2 transit OK local OpenCV + local MediaPipe, zero network egress
# API 4.1 rate limit    OK frame rate default 10 fps, hard cap 30 fps
# Privacy 5.1 opt-in    OK default OFF (_enabled = False), must call start()
# Privacy 5.4 sensitive OK no frame storage, no disk write, no cloud upload from this module
# Incident 7.3 kill     OK env CAMERA_DISABLE=1 + stop() via threading.Event <= 200ms
# Incident 7.1 audit    OK start / stop / periodic stats logged to stderr (no disk write)
#
# ADR-018 3 tests:
# - webcam Wireshark zero egress   OK local capture + local inference, no network in this module
# - disk scan zero residue          OK fully RAM, no cv2.imwrite or file write anywhere
# - kill switch <= 200ms            OK threading.Event.set() + cap.release() immediate
# =================================================================

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("castle.multimodal.camera")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s"))
    logger.addHandler(_h)


DEFAULT_FPS = 10
MAX_FPS = 30
DEFAULT_CAMERA_INDEX = 0
KILL_TIMEOUT_S = 0.2
MEDIAPIPE_AVAILABLE = False
OPENCV_AVAILABLE = False

try:
    import cv2
    OPENCV_AVAILABLE = True
except Exception as e:
    logger.warning("opencv-python-headless not available: %s - camera disabled", e)

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except Exception as e:
    logger.warning("mediapipe not available: %s - landmark inference disabled", e)


@dataclass
class FrameStat:
    frame_count: int = 0
    last_frame_ts: float = 0.0
    last_inference_ts: float = 0.0
    fps_actual: float = 0.0
    width: int = 0
    height: int = 0


@dataclass
class Landmarks:
    face_present: bool = False
    face_landmarks: Optional[list] = None
    pose_present: bool = False
    pose_landmarks: Optional[list] = None
    hands_present: bool = False
    hand_landmarks: list = field(default_factory=list)
    timestamp: float = 0.0


class CameraManager:
    """Singleton webcam manager. Privacy default OFF, must explicitly start()."""

    def __init__(self, camera_index=DEFAULT_CAMERA_INDEX, fps=DEFAULT_FPS):
        self.camera_index = camera_index
        self.fps = min(max(1, fps), MAX_FPS)
        self._enabled = False
        self._stop_event = threading.Event()
        self._capture_thread = None
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_landmarks = Landmarks()
        self._stat = FrameStat()
        self._cap = None
        self._face_mesh = None
        self._pose = None
        self._hands = None
        # Privacy 5.1: initial state fully OFF
        logger.info("CameraManager init - idx=%s fps=%s - DISABLED by default (Privacy 5.1)", camera_index, fps)

    def is_enabled(self):
        return self._enabled

    def is_available(self):
        if os.environ.get("CAMERA_DISABLE", "").strip() in ("1", "true", "yes"):
            return False
        return OPENCV_AVAILABLE

    def start(self):
        # Privacy 5.1 + Incident 7.3: env kill switch precedence
        if os.environ.get("CAMERA_DISABLE", "").strip() in ("1", "true", "yes"):
            logger.warning("CAMERA_DISABLE env set - start refused")
            return {"ok": False, "error": "camera_disabled_by_env", "detail": "CAMERA_DISABLE=1 set"}
        if not OPENCV_AVAILABLE:
            return {"ok": False, "error": "opencv_unavailable", "detail": "opencv-python-headless not installed"}
        if self._enabled:
            return {"ok": True, "already_enabled": True, "stat": self._stat_dict()}
        try:
            self._cap = cv2.VideoCapture(self.camera_index)
            if not self._cap.isOpened():
                self._cap = None
                logger.error("VideoCapture(%s) failed", self.camera_index)
                return {"ok": False, "error": "webcam_open_failed", "detail": "VideoCapture not opened"}
        except Exception as e:
            logger.error("webcam open exception: %s", e)
            return {"ok": False, "error": "webcam_open_exception", "detail": str(e)}
        if MEDIAPIPE_AVAILABLE:
            try:
                mp_face = mp.solutions.face_mesh
                mp_pose = mp.solutions.pose
                mp_hands = mp.solutions.hands
                self._face_mesh = mp_face.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=False, min_detection_confidence=0.5, min_tracking_confidence=0.5)
                self._pose = mp_pose.Pose(static_image_mode=False, model_complexity=1, min_detection_confidence=0.5, min_tracking_confidence=0.5)
                self._hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5, min_tracking_confidence=0.5)
            except Exception as e:
                logger.warning("MediaPipe init failed: %s - landmarks disabled this session", e)
                self._face_mesh = None
                self._pose = None
                self._hands = None
        self._stop_event.clear()
        self._enabled = True
        self._capture_thread = threading.Thread(target=self._capture_loop, name="cve-camera-capture", daemon=True)
        self._capture_thread.start()
        logger.info("CAMERA START - index=%s fps=%s mediapipe=%s", self.camera_index, self.fps, MEDIAPIPE_AVAILABLE)
        return {"ok": True, "enabled": True, "camera_index": self.camera_index, "fps": self.fps, "mediapipe_available": MEDIAPIPE_AVAILABLE}

    def stop(self):
        if not self._enabled:
            return {"ok": True, "already_disabled": True}
        self._stop_event.set()
        self._enabled = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        self._release_resources()
        logger.info("CAMERA STOP - final_stat=%s", self._stat_dict())
        return {"ok": True, "stopped": True, "stat": self._stat_dict()}

    def kill(self):
        # Incident 7.3: emergency stop <= 200ms
        t0 = time.time()
        self._stop_event.set()
        self._enabled = False
        try:
            self._release_resources()
        except Exception as e:
            logger.error("kill release error: %s", e)
        elapsed_ms = (time.time() - t0) * 1000.0
        logger.warning("CAMERA KILL - elapsed=%.1fms (target <= %.1fms)", elapsed_ms, KILL_TIMEOUT_S * 1000)
        return {"ok": True, "killed": True, "elapsed_ms": round(elapsed_ms, 1), "target_ms": KILL_TIMEOUT_S * 1000}

    def get_latest_frame(self):
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def get_latest_landmarks(self):
        with self._lock:
            return self._latest_landmarks

    def status(self):
        return {
            "enabled": self._enabled,
            "available": self.is_available(),
            "opencv_available": OPENCV_AVAILABLE,
            "mediapipe_available": MEDIAPIPE_AVAILABLE,
            "kill_env_set": os.environ.get("CAMERA_DISABLE", "").strip() in ("1", "true", "yes"),
            "camera_index": self.camera_index,
            "fps": self.fps,
            "stat": self._stat_dict(),
        }

    def _capture_loop(self):
        frame_period = 1.0 / float(self.fps)
        last_log = time.time()
        frames_since_log = 0
        while not self._stop_event.is_set():
            t_start = time.time()
            try:
                if self._cap:
                    ok, frame = self._cap.read()
                else:
                    ok, frame = False, None
            except Exception as e:
                logger.error("capture read exception: %s", e)
                ok = False
                frame = None
            if ok and frame is not None:
                if MEDIAPIPE_AVAILABLE:
                    landmarks = self._infer_landmarks(frame)
                else:
                    landmarks = Landmarks(timestamp=time.time())
                with self._lock:
                    self._latest_frame = frame
                    self._latest_landmarks = landmarks
                    self._stat.frame_count += 1
                    self._stat.last_frame_ts = time.time()
                    self._stat.height, self._stat.width = frame.shape[:2]
                    if landmarks.face_present or landmarks.pose_present or landmarks.hands_present:
                        self._stat.last_inference_ts = time.time()
                frames_since_log += 1
            now = time.time()
            if now - last_log >= 10.0:
                self._stat.fps_actual = frames_since_log / (now - last_log)
                logger.info("camera frame_count=%s fps=%.1f size=%sx%s lm=%s/%s/%s", self._stat.frame_count, self._stat.fps_actual, self._stat.width, self._stat.height, self._latest_landmarks.face_present, self._latest_landmarks.pose_present, self._latest_landmarks.hands_present)
                last_log = now
                frames_since_log = 0
            elapsed = time.time() - t_start
            if elapsed < frame_period:
                self._stop_event.wait(timeout=frame_period - elapsed)
        logger.info("capture loop exit cleanly")

    def _infer_landmarks(self, frame):
        result = Landmarks(timestamp=time.time())
        if not MEDIAPIPE_AVAILABLE:
            return result
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            if self._face_mesh is not None:
                fm_res = self._face_mesh.process(rgb)
                if fm_res.multi_face_landmarks:
                    pts = fm_res.multi_face_landmarks[0].landmark
                    result.face_present = True
                    keypoint_idx = [33, 263, 1, 61, 291, 199, 17, 10]
                    result.face_landmarks = [{"x": pts[i].x, "y": pts[i].y, "z": pts[i].z} for i in keypoint_idx if i < len(pts)]
            if self._pose is not None:
                pose_res = self._pose.process(rgb)
                if pose_res.pose_landmarks:
                    pts = pose_res.pose_landmarks.landmark
                    result.pose_present = True
                    result.pose_landmarks = [{"x": p.x, "y": p.y, "z": p.z, "v": p.visibility} for p in pts]
            if self._hands is not None:
                hands_res = self._hands.process(rgb)
                if hands_res.multi_hand_landmarks:
                    result.hands_present = True
                    result.hand_landmarks = []
                    for hand in hands_res.multi_hand_landmarks:
                        result.hand_landmarks.append([{"x": p.x, "y": p.y, "z": p.z} for p in hand.landmark])
        except Exception as e:
            logger.warning("MediaPipe inference error: %s", e)
        return result

    def _release_resources(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        for attr in ("_face_mesh", "_pose", "_hands"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)
        with self._lock:
            # Privacy 5.4: drop frame buffer immediately
            self._latest_frame = None

    def _stat_dict(self):
        return {
            "frame_count": self._stat.frame_count,
            "fps_actual": round(self._stat.fps_actual, 2),
            "width": self._stat.width,
            "height": self._stat.height,
            "last_frame_age_s": (round(time.time() - self._stat.last_frame_ts, 2) if self._stat.last_frame_ts else None),
        }


_singleton = None
_singleton_lock = threading.Lock()


def get_camera_manager():
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = CameraManager()
        return _singleton
