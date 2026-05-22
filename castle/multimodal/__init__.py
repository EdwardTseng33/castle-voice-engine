# castle-voice-engine — (c) 2026 Edward / BeyondPath
# castle/multimodal/__init__.py
#
# Phase 3 (v0.3.0): camera + MediaPipe + Claude vision narration.
# Privacy default: OFF. User must explicitly POST /camera/enable to start.

from castle.multimodal.camera import CameraManager, get_camera_manager
from castle.multimodal.vision_analyzer import VisionAnalyzer, get_vision_analyzer

__all__ = [
    "CameraManager",
    "get_camera_manager",
    "VisionAnalyzer",
    "get_vision_analyzer",
]
