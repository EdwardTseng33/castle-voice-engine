# castle-voice-engine - (c) 2026 Edward / BeyondPath
# castle/multimodal/pose_hands_dispatch.py
#
# v1.1.3 (2026-05-23) - MediaPipe Pose + Hands state dispatcher.
#
# Companion rhythm: detect Edward body language and emit animation signals.
# Pose + Hands inference is LOCAL ONLY. ndarray dropped after each frame.
#
# Privacy compliance (inherits camera.py guarantees):
# Data flow 1.1-1.6     OK frame ndarray dropped after process()
# IAM 2.4 token         OK no token handling
# Encryption 3.2 transit OK fully local inference, zero network egress
# API 4.1 rate limit    OK ~5 fps processing
# Privacy 5.1 opt-in    OK only runs when CameraManager passes frames in
# Privacy 5.4 sensitive OK no frame storage; cooldown debounces emits
# Incident 7.3 kill     OK dispatcher state cleared when camera stops
# Incident 7.1 audit    OK transitions logged (no frame content)
#
# State machine: present / absent / waving / chin_rest / hands_up
# Cooldown 4s between same-state re-emits. Same-state = no signal.

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("castle.multimodal.pose_hands_dispatch")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s"))
    logger.addHandler(_h)


MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except Exception as e:
    logger.warning("mediapipe not available: %s - pose/hands dispatch disabled", e)


DEFAULT_COOLDOWN_S = 4.0
POSE_MIN_CONF = 0.6
HANDS_MIN_CONF = 0.6
ABSENT_FRAMES_REQUIRED = 4
WAVE_Y_MARGIN = 0.05
CHIN_X_TOL = 0.12
CHIN_Y_TOL = 0.10
HANDS_UP_MARGIN = 0.04


@dataclass
class DispatchStat:
    frames_processed: int = 0
    transitions: int = 0
    suppressed_by_cooldown: int = 0
    last_state: str = "present"
    last_transition_ts: float = 0.0
    state_counts: dict = field(default_factory=dict)


STATE_TO_SIGNAL = {
    "absent":    {"animation": "task-handoff",    "reason": "edward_left_frame"},
    "waving":    {"animation": "acknowledgement", "reason": "edward_waved"},
    "chin_rest": {"animation": "acknowledgement", "reason": "edward_thinking"},
    "hands_up":  {"animation": "playful",         "reason": "edward_excited"},
    "present":   None,
    "returning": {"animation": "greeting",        "reason": "edward_returned"},
}


class PoseHandsDispatcher:
    def __init__(self, cooldown_s=DEFAULT_COOLDOWN_S):
        self.cooldown_s = cooldown_s
        self.state = "present"
        self.last_emit_t = 0.0
        self._pose = None
        self._hands = None
        self._absent_counter = 0
        self._stat = DispatchStat()
        self._init_models()

    def _init_models(self):
        if not MEDIAPIPE_AVAILABLE:
            return
        try:
            mp_pose = mp.solutions.pose
            mp_hands = mp.solutions.hands
            self._pose = mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                min_detection_confidence=POSE_MIN_CONF,
                min_tracking_confidence=POSE_MIN_CONF,
            )
            self._hands = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=HANDS_MIN_CONF,
                min_tracking_confidence=HANDS_MIN_CONF,
            )
            logger.info("PoseHandsDispatcher models loaded")
        except Exception as e:
            logger.warning("PoseHandsDispatcher init fail: %s", e)
            self._pose = None
            self._hands = None

    def is_available(self):
        return MEDIAPIPE_AVAILABLE and self._pose is not None and self._hands is not None

    def close(self):
        for attr in ("_pose", "_hands"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)
        logger.info("PoseHandsDispatcher closed - final_stat=%s", self.stat_dict())

    def reset_state(self):
        self.state = "present"
        self.last_emit_t = 0.0
        self._absent_counter = 0

    def process(self, frame_rgb):
        if not self.is_available():
            return None
        if frame_rgb is None:
            return None
        self._stat.frames_processed += 1
        try:
            frame_rgb.flags.writeable = False
            pose_res = self._pose.process(frame_rgb)
            hand_res = self._hands.process(frame_rgb)
        except Exception as e:
            logger.warning("pose/hands process err: %s", e)
            return None
        new_state = self._classify(pose_res, hand_res)
        return self._maybe_emit(new_state)

    def _classify(self, pose_res, hand_res):
        if not getattr(pose_res, "pose_landmarks", None):
            self._absent_counter += 1
            if self._absent_counter >= ABSENT_FRAMES_REQUIRED:
                return "absent"
            return self.state if self.state != "absent" else "absent"
        self._absent_counter = 0
        plm = pose_res.pose_landmarks.landmark
        try:
            nose = plm[0]
            l_sh = plm[11]
            r_sh = plm[12]
            mouth_l = plm[9]
            mouth_r = plm[10]
            chin_x = (mouth_l.x + mouth_r.x) / 2.0
            chin_y = (mouth_l.y + mouth_r.y) / 2.0 + 0.05
            shoulder_mid_y = (l_sh.y + r_sh.y) / 2.0
        except Exception:
            return "present"
        hands = []
        if getattr(hand_res, "multi_hand_landmarks", None):
            for h in hand_res.multi_hand_landmarks:
                try:
                    w = h.landmark[0]
                    hands.append({"x": w.x, "y": w.y})
                except Exception:
                    pass
        if len(hands) >= 2:
            both_above = all(hd["y"] < shoulder_mid_y - HANDS_UP_MARGIN for hd in hands[:2])
            if both_above:
                return "hands_up"
        for h in hands:
            if h["y"] < nose.y - WAVE_Y_MARGIN:
                return "waving"
        for h in hands:
            if abs(h["x"] - chin_x) < CHIN_X_TOL and abs(h["y"] - chin_y) < CHIN_Y_TOL:
                return "chin_rest"
        return "present"

    def _maybe_emit(self, new_state):
        now = time.time()
        prev_state = self.state
        if new_state == prev_state:
            self._stat.state_counts[new_state] = self._stat.state_counts.get(new_state, 0) + 1
            return None
        if (now - self.last_emit_t) < self.cooldown_s:
            self._stat.suppressed_by_cooldown += 1
            return None
        self.state = new_state
        self.last_emit_t = now
        self._stat.transitions += 1
        self._stat.last_state = new_state
        self._stat.last_transition_ts = now
        self._stat.state_counts[new_state] = self._stat.state_counts.get(new_state, 0) + 1
        if prev_state == "absent" and new_state == "present":
            sig = STATE_TO_SIGNAL.get("returning")
        else:
            sig = STATE_TO_SIGNAL.get(new_state)
        if sig is None:
            logger.info("pose/hands %s -> %s (no signal)", prev_state, new_state)
            return None
        payload = {
            "animation": sig["animation"],
            "reason": sig["reason"],
            "source": "pose_hands",
            "from": prev_state,
            "to": new_state,
            "ts": now,
        }
        logger.info("pose/hands SIGNAL %s -> %s anim=%s", prev_state, new_state, sig["animation"])
        return payload

    def get_state(self):
        return self.state

    def get_absent_seconds(self):
        if self.state != "absent":
            return 0.0
        return max(0.0, time.time() - self.last_emit_t)

    def stat_dict(self):
        return {
            "frames_processed": self._stat.frames_processed,
            "transitions": self._stat.transitions,
            "suppressed_by_cooldown": self._stat.suppressed_by_cooldown,
            "last_state": self._stat.last_state,
            "last_transition_ts": round(self._stat.last_transition_ts, 2),
            "current_state": self.state,
            "state_counts": dict(self._stat.state_counts),
            "available": self.is_available(),
        }


_singleton = None
_singleton_lock = threading.Lock()


def get_pose_hands_dispatcher():
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = PoseHandsDispatcher()
        return _singleton
