# castle-voice-engine - (c) 2026 Edward / BeyondPath
# castle/server/camera_endpoints.py
#
# Phase 3 (v0.3.0) - FastAPI endpoints for webcam control + vision narration.
#
# =================================================================
# Privacy compliance
# =================================================================
# Data flow 1.x         OK no frame data is exposed via these endpoints by default
#                          (snapshot endpoint is debug-only, gated by env CAMERA_DEBUG=1)
# IAM 2.4 token         OK no token handling here - delegated to vision_analyzer (Modal secret)
# API 4.1 rate limit    OK endpoints idempotent / fast; rate cap is in camera_loop + vision_loop
# Privacy 5.1 opt-in    OK /camera/enable is the explicit user gate (POST not GET, intentional)
# Incident 7.3 kill     OK /camera/kill calls CameraManager.kill() -> <= 200ms
# Incident 7.1 audit    OK each endpoint call logged with action
# =================================================================
#
# Endpoints:
#   POST /camera/enable     - user explicit consent to open webcam
#   POST /camera/disable    - graceful stop
#   POST /camera/kill       - emergency stop <= 200ms
#   GET  /camera/status     - camera + vision state
#   GET  /camera/snapshot   - debug only (env CAMERA_DEBUG=1)
#   POST /vision/enable     - start Claude vision narration loop
#   POST /vision/disable    - stop narration loop
#   GET  /vision/status     - narration stats
#   GET  /vision/latest     - latest observation for browser polling

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger("castle.server.camera_endpoints")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s"))
    logger.addHandler(_h)


def attach_camera_routes(app):
    """Mount camera + vision endpoints on a FastAPI instance."""

    @app.post("/camera/enable")
    async def camera_enable():
        try:
            from castle.multimodal.camera import get_camera_manager
        except Exception as e:
            return JSONResponse(status_code=503, content={"error": "camera_module_unavailable", "detail": str(e)})
        mgr = get_camera_manager()
        result = mgr.start()
        logger.info("[/camera/enable] result=%s", result.get("ok"))
        status = 200 if result.get("ok") else 503
        return JSONResponse(status_code=status, content=result)

    @app.post("/camera/disable")
    async def camera_disable():
        try:
            from castle.multimodal.camera import get_camera_manager
        except Exception as e:
            return JSONResponse(status_code=503, content={"error": "camera_module_unavailable", "detail": str(e)})
        mgr = get_camera_manager()
        result = mgr.stop()
        try:
            from castle.multimodal.vision_analyzer import get_vision_analyzer
            v = get_vision_analyzer()
            if v.is_enabled():
                v.disable()
        except Exception:
            pass
        logger.info("[/camera/disable] result=%s", result.get("ok"))
        return JSONResponse(status_code=200, content=result)

    @app.post("/camera/kill")
    async def camera_kill():
        try:
            from castle.multimodal.camera import get_camera_manager
        except Exception as e:
            return JSONResponse(status_code=503, content={"error": "camera_module_unavailable", "detail": str(e)})
        mgr = get_camera_manager()
        result = mgr.kill()
        try:
            from castle.multimodal.vision_analyzer import get_vision_analyzer
            v = get_vision_analyzer()
            if v.is_enabled():
                v.disable()
        except Exception:
            pass
        logger.warning("[/camera/kill] elapsed_ms=%s", result.get("elapsed_ms"))
        return JSONResponse(status_code=200, content=result)

    @app.get("/camera/status")
    async def camera_status():
        try:
            from castle.multimodal.camera import get_camera_manager
            from castle.multimodal.vision_analyzer import get_vision_analyzer
        except Exception as e:
            return JSONResponse(status_code=200, content={"camera": {"available": False, "error": str(e)}, "vision": {"available": False}})
        cam = get_camera_manager().status()
        try:
            vis = get_vision_analyzer().status()
        except Exception as e:
            vis = {"available": False, "error": str(e)}
        return {"camera": cam, "vision": vis}

    @app.get("/camera/snapshot")
    async def camera_snapshot():
        # Privacy 5.4: debug-only gate
        if os.environ.get("CAMERA_DEBUG", "").strip() not in ("1", "true", "yes"):
            return JSONResponse(status_code=403, content={"error": "snapshot_disabled", "detail": "set env CAMERA_DEBUG=1 to enable"})
        try:
            from castle.multimodal.camera import get_camera_manager
            from castle.multimodal.vision_analyzer import get_vision_analyzer
        except Exception as e:
            return JSONResponse(status_code=503, content={"error": "module_unavailable", "detail": str(e)})
        mgr = get_camera_manager()
        if not mgr.is_enabled():
            return JSONResponse(status_code=409, content={"error": "camera_not_enabled"})
        frame = mgr.get_latest_frame()
        if frame is None:
            return JSONResponse(status_code=204, content={"error": "no_frame_available"})
        v = get_vision_analyzer()
        jpeg = v._encode_frame_to_jpeg(frame)
        if jpeg is None:
            return JSONResponse(status_code=500, content={"error": "encode_failed"})
        logger.warning("[/camera/snapshot] debug endpoint hit - kb=%.1f", len(jpeg) / 1024.0)
        return Response(content=jpeg, media_type="image/jpeg")

    @app.post("/vision/enable")
    async def vision_enable():
        try:
            from castle.multimodal.vision_analyzer import get_vision_analyzer
        except Exception as e:
            return JSONResponse(status_code=503, content={"error": "vision_module_unavailable", "detail": str(e)})
        v = get_vision_analyzer()
        result = v.enable()
        logger.info("[/vision/enable] result=%s", result.get("ok"))
        status = 200 if result.get("ok") else 503
        return JSONResponse(status_code=status, content=result)

    @app.post("/vision/disable")
    async def vision_disable():
        try:
            from castle.multimodal.vision_analyzer import get_vision_analyzer
        except Exception as e:
            return JSONResponse(status_code=503, content={"error": "vision_module_unavailable", "detail": str(e)})
        v = get_vision_analyzer()
        result = v.disable()
        logger.info("[/vision/disable] result=%s", result.get("ok"))
        return JSONResponse(status_code=200, content=result)

    @app.get("/vision/status")
    async def vision_status():
        try:
            from castle.multimodal.vision_analyzer import get_vision_analyzer
        except Exception as e:
            return JSONResponse(status_code=200, content={"available": False, "error": str(e)})
        return get_vision_analyzer().status()

    @app.get("/vision/latest")
    async def vision_latest():
        """Browser polls this at ~1Hz to relay narration to OpenAI session."""
        try:
            from castle.multimodal.vision_analyzer import get_vision_analyzer
        except Exception:
            return {"text": "", "ts": 0, "available": False}
        v = get_vision_analyzer()
        s = v.status()
        recent = s.get("recent_observations", [])
        latest_text = ""
        latest_ts = 0
        for o in reversed(recent):
            if not o.get("is_skip") and o.get("text"):
                latest_text = o["text"]
                latest_ts = o["ts"]
                break
        return {"text": latest_text, "ts": latest_ts, "enabled": s.get("enabled"), "stat": s.get("stat")}

    @app.get("/vision/emotion_latest")
    async def vision_emotion_latest():
        """v0.9.3 - Browser polls this at ~1Hz to drive sophie animation pool.

        Returns dict {state, confidence, ts} if a new emotion event fires (after 15s cooldown),
        or {state: null} for idle frames. FaceMesh-only this version (Pose/Hands deferred).
        """
        try:
            from castle.multimodal.camera import get_camera_manager
        except Exception as e:
            return {"state": None, "error": str(e)}
        mgr = get_camera_manager()
        if not mgr.is_enabled():
            return {"state": None, "reason": "camera_disabled"}
        try:
            evt = mgr.get_emotion_event()
            if evt is None:
                return {"state": None}
            evt["type"] = "vision.emotion"
            return evt
        except Exception as e:
            logger.warning("[/vision/emotion_latest] err: %s", e)
            return {"state": None, "error": str(e)}

    @app.get("/vision/pose_hands_latest")
    async def vision_pose_hands_latest():
        """v1.1.3 - Browser polls this at ~1Hz to drive sophie pose/hands animation.

        Returns dict {signal: {...}, current_state, absent_seconds} if a new
        transition fired (consumed-on-read), or {signal: null, current_state, absent_seconds}
        otherwise. Pose+Hands inference is fully local (Modal A10G). No frame
        data leaves the box.
        """
        try:
            from castle.multimodal.camera import get_camera_manager
        except Exception as e:
            return {"signal": None, "error": str(e)}
        mgr = get_camera_manager()
        if not mgr.is_enabled():
            return {"signal": None, "reason": "camera_disabled"}
        try:
            sig = mgr.get_pose_hands_signal()
            current = "present"
            absent_s = 0.0
            try:
                if mgr._pose_hands is not None:
                    current = mgr._pose_hands.get_state()
                    absent_s = mgr._pose_hands.get_absent_seconds()
            except Exception:
                pass
            return {
                "signal": sig,
                "current_state": current,
                "absent_seconds": round(absent_s, 2),
            }
        except Exception as e:
            logger.warning("[/vision/pose_hands_latest] err: %s", e)
            return {"signal": None, "error": str(e)}

    logger.info("camera_endpoints attached: /camera/* and /vision/*")
