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

try:
    from castle.multimodal.pose_hands_dispatch import get_pose_hands_dispatcher
    POSE_HANDS_DISPATCH_AVAILABLE = True
except Exception as e:
    POSE_HANDS_DISPATCH_AVAILABLE = False
    logger.warning("pose_hands_dispatch not available: %s", e)


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
        # v1.1.3 pose/hands dispatcher (transitions -> animation signals)
        self._pose_hands = None
        self._pose_hands_signal = None  # latest unread signal (consumed-on-read)
        self._pose_hands_frame_skip = 0
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
                # v1.1.3 pose/hands dispatcher (separate models, finer state machine)
                if POSE_HANDS_DISPATCH_AVAILABLE:
                    try:
                        self._pose_hands = get_pose_hands_dispatcher()
                        if self._pose_hands is not None:
                            self._pose_hands.reset_state()
                    except Exception as ph_e:
                        logger.warning("pose_hands init failed: %s", ph_e)
                        self._pose_hands = None
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
            "pose_hands": self.pose_hands_status(),
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
                    # v0.9.3 emotion-relevant FaceMesh indices (subset of 468)
                    # eye corners (33 / 263) - eye openness (159 145 / 386 374) -
                    # nose (1) - mouth corners (61 / 291) - mouth top/bot (13 / 14)
                    # chin (17 / 199) - forehead (10) - brows (9 / 8 - inner brow midpoint)
                    keypoint_idx = [33, 133, 159, 145, 263, 362, 386, 374, 1, 61, 291, 13, 14, 17, 199, 10, 9, 8]
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
        # v1.1.3 - run PoseHands dispatcher every 2nd frame (5 fps if capture is 10 fps)
        # ndarray ownership: we keep rgb local; dispatcher reads, drops ref on return
        try:
            if self._pose_hands is not None and self._pose_hands.is_available():
                self._pose_hands_frame_skip = (self._pose_hands_frame_skip + 1) % 2
                if self._pose_hands_frame_skip == 0:
                    # Re-derive RGB if needed (rgb defined in try-block above; safe re-eval)
                    try:
                        rgb_for_ph = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        sig = self._pose_hands.process(rgb_for_ph)
                        if sig is not None:
                            with self._lock:
                                self._pose_hands_signal = sig
                    except Exception as ph_proc_e:
                        logger.warning("pose_hands dispatch err: %s", ph_proc_e)
        except Exception as ph_outer_e:
            logger.warning("pose_hands outer err: %s", ph_outer_e)
        return result

    def _release_resources(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        # v1.1.3 close pose/hands dispatcher cleanly
        try:
            if self._pose_hands is not None:
                self._pose_hands.close()
        except Exception:
            pass
        self._pose_hands = None
        self._pose_hands_signal = None
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

    # ===== v0.9.3 Emotion Detection (FaceMesh-only · Pose/Hands deferred) =====
    # Edward 2026-05-23 spec: docs/v0.9-animation-pool-design.md § 4.1 + § 4.4
    # 表情類觸發: happy / apologetic / acknowledgement / resigned
    # 注視類觸發: gaze_present / gaze_absent
    # 15s cooldown per state · confidence >= 0.7 only

    EMOTION_COOLDOWN_S = 15.0
    GAZE_PRESENT_S    = 3.0   # face seen 3s+ = gaze_present
    GAZE_ABSENT_S     = 30.0  # face gone 30s+ = gaze_absent

    def detect_emotion(self):
        """Read latest landmarks + return (state, confidence) or (None, 0). v0.9.3 FaceMesh-only.

        Returns one of: happy / apologetic / acknowledgement / resigned / playful / None
        Confidence in [0, 1]. None means no signal detected this frame."""
        lm = self.get_latest_landmarks()
        if not lm or not lm.face_present or not lm.face_landmarks:
            return (None, 0.0)
        try:
            pts = lm.face_landmarks
            # Layout (after v0.9.3 expansion):
            # 0=eye33  1=eye133  2=eye159  3=eye145  4=eye263  5=eye362  6=eye386  7=eye374
            # 8=nose1  9=mouth_l61  10=mouth_r291  11=lip_top13  12=lip_bot14
            # 13=chin17  14=chin199  15=fhead10  16=brow9  17=brow8
            if len(pts) < 18:
                return (None, 0.0)

            mouth_l = pts[9]
            mouth_r = pts[10]
            lip_top = pts[11]
            lip_bot = pts[12]
            eye_l_top = pts[2]; eye_l_bot = pts[3]
            eye_l_out = pts[0]; eye_l_in  = pts[1]
            eye_r_top = pts[6]; eye_r_bot = pts[7]
            eye_r_out = pts[4]; eye_r_in  = pts[5]
            brow_l = pts[16]; brow_r = pts[17]
            chin   = pts[14]
            fhead  = pts[15]

            # EAR (Eye Aspect Ratio): vertical / horizontal opening
            def ear(top, bot, out, inn):
                v = abs(top["y"] - bot["y"])
                h = abs(out["x"] - inn["x"])
                return v / h if h > 1e-6 else 0
            ear_l = ear(eye_l_top, eye_l_bot, eye_l_out, eye_l_in)
            ear_r = ear(eye_r_top, eye_r_bot, eye_r_out, eye_r_in)
            ear_avg = (ear_l + ear_r) / 2

            # Mouth aspect: vertical / horizontal (uses lip pair + mouth corners)
            mouth_v = abs(lip_top["y"] - lip_bot["y"])
            mouth_h = abs(mouth_l["x"] - mouth_r["x"])
            mouth_aspect = mouth_v / mouth_h if mouth_h > 1e-6 else 0

            # Mouth corner angle relative to lip midline (sign-aware)
            mid_y = (lip_top["y"] + lip_bot["y"]) / 2
            # Negative = corners above midline (smile); positive = below (frown)
            avg_corner_y = (mouth_l["y"] + mouth_r["y"]) / 2
            corner_offset = avg_corner_y - mid_y

            # Brow distance (inner brow points; smaller = more frown)
            brow_gap = abs(brow_l["x"] - brow_r["x"])

            # ---- Decision (priority: surprised -> sad -> happy -> resigned -> none) ----
            # All thresholds normalized (FaceMesh coords are 0..1 of frame size)

            # Surprised (mouth open wide + eyes wider than baseline) -> acknowledgement
            if mouth_aspect > 0.55 and ear_avg > 0.35:
                return ("acknowledgement", min(1.0, mouth_aspect * 1.4))

            # Sad / Frown (corners droop below midline + brow gap narrow) -> apologetic
            if corner_offset > 0.012 and brow_gap < 0.045:
                conf = min(1.0, (corner_offset / 0.025) * 0.7 + (0.045 - brow_gap) / 0.045 * 0.3)
                return ("apologetic", conf)

            # Happy / Smile (corners above midline + mouth wider) -> happy
            if corner_offset < -0.010 and mouth_h > 0.060:
                conf = min(1.0, abs(corner_offset) / 0.020 * 0.75 + (mouth_h / 0.10) * 0.25)
                return ("happy", conf)

            # Resigned (eye half-closed + neutral mouth) -> resigned
            if ear_avg < 0.18 and abs(corner_offset) < 0.005:
                conf = min(1.0, (0.18 - ear_avg) / 0.18 * 0.8 + 0.2)
                return ("resigned", conf)

            return (None, 0.0)
        except Exception as e:
            logger.warning("emotion detect fail: %s", e)
            return (None, 0.0)

    # ===== v0.9.3 Emotion cooldown / dedup =====
    # _last_emotion_emit: state -> ts; called by /vision/emotion_latest endpoint
    def get_emotion_event(self):
        """Snapshot emotion (with cooldown). Returns dict or None."""
        state, conf = self.detect_emotion()
        if not state or conf < 0.7:
            return None
        if not hasattr(self, "_last_emotion_emit"):
            self._last_emotion_emit = {}
        now = time.time()
        last = self._last_emotion_emit.get(state, 0)
        if now - last < self.EMOTION_COOLDOWN_S:
            return None
        self._last_emotion_emit[state] = now
        return {"state": state, "confidence": round(conf, 3), "ts": now}

    def get_pose_hands_signal(self):
        """Return latest pose/hands signal (and consume it). Returns dict or None."""
        with self._lock:
            sig = self._pose_hands_signal
            self._pose_hands_signal = None
            return sig

    def pose_hands_status(self):
        """Return pose/hands dispatcher stat dict (or unavailable marker)."""
        if self._pose_hands is None:
            return {"available": False}
        try:
            return self._pose_hands.stat_dict()
        except Exception as e:
            return {"available": False, "error": str(e)}


_singleton = None
_singleton_lock = threading.Lock()


def get_camera_manager():
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = CameraManager()
        return _singleton
