# castle-voice-engine - v0.3.0 Phase 2 (Path B)
# castle/server/picovoice_stub.py
#
# PLACEHOLDER - Phase 2 後半段 wake-word + on-device VAD via Picovoice (pveagle
# already SDK-verified in breeze_poc Day 4 Stage 3). This file holds the
# integration scaffold so wiring is a 5-minute job once Edward pastes
# PICOVOICE_ACCESS_KEY into Modal secret 'voice-path-daemon'.
#
# Why staged: Picovoice requires Edward to log into https://console.picovoice.ai
# and grab an AccessKey (free tier 3-user). That step has to be human-in-loop.
# See EDWARD-PICOVOICE-2-STEPS.md in repo root for the 2-step flow.
#
# Once AccessKey is in place, unlock = uncomment the import + flip
# IS_ENABLED = True. The /wake-status endpoint will start returning real state.

from __future__ import annotations

import os

IS_ENABLED = False  # flip to True after AccessKey lands in Modal secret


def is_enabled() -> bool:
    """Whether Picovoice wake-word layer is active. False = use OpenAI server_vad only."""
    return IS_ENABLED and bool(os.environ.get("PICOVOICE_ACCESS_KEY", "").strip())


def status() -> dict:
    """Returns dict describing wake-word layer state. Safe to call any time."""
    key_present = bool(os.environ.get("PICOVOICE_ACCESS_KEY", "").strip())
    return {
        "enabled": IS_ENABLED,
        "access_key_present": key_present,
        "ready": IS_ENABLED and key_present,
        "fallback": "openai_server_vad" if not (IS_ENABLED and key_present) else None,
        "next_step": None if (IS_ENABLED and key_present) else "see EDWARD-PICOVOICE-2-STEPS.md in repo root",
        "sdk_verified": True,  # pveagle 3.0.2 SDK installable, verified in breeze_poc Day 4 Stage 3
        "phase": "placeholder",
    }


# --- Future wiring (uncomment after AccessKey arrives) -----------------------
#
# import pveagle
#
# _PROFILER = None
# _RECOGNIZER = None
#
# def init_profiler():
#     global _PROFILER
#     access_key = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()
#     if not access_key:
#         raise RuntimeError("PICOVOICE_ACCESS_KEY missing")
#     _PROFILER = pveagle.create_profiler(access_key=access_key)
#     return _PROFILER
#
# def init_recognizer(speaker_profiles: list):
#     global _RECOGNIZER
#     access_key = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()
#     _RECOGNIZER = pveagle.create_recognizer(
#         access_key=access_key,
#         speaker_profiles=speaker_profiles,
#     )
#     return _RECOGNIZER
