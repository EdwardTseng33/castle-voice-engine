# castle-voice-engine talking-head adapter for MuseTalk v1.5
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
# Voice Path v0.7 · 三層架構「嘴」這層 thin client
#   Server: castle-voice-engine-musetalk-poc.modal.run (breeze_poc/app_musetalk.py)
#   接口:    /musetalk/health · /musetalk/stream (WebSocket)
#
# v0.3.0 (2026-05-26): 移除錯誤建立的 Sally hard rule (記憶污染 · 詳 CHANGELOG)

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Optional, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# Log header (sulima audit C4 requirement)
logger.info(
    "[v0.7] talking-head: MuseTalk v1.5 (MIT, Lyra Lab/Tencent Music Entertainment)"
)


@dataclass(frozen=True)
class MuseTalkConfig:
    base_url: str
    auth_token: str
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "MuseTalkConfig":
        base = os.environ.get(
            "MUSETALK_BASE_URL",
            "https://edwardt0303--castle-voice-engine-musetalk-poc-fastapi-app.modal.run",
        )
        token = os.environ.get("MUSETALK_AUTH_TOKEN", "")
        if not token:
            raise RuntimeError(
                "MUSETALK_AUTH_TOKEN not set · set Modal secret musetalk-poc-auth first"
            )
        return cls(base_url=base.rstrip("/"), auth_token=token)


class MuseTalkClient:
    """Thin async client for the MuseTalk Modal app."""

    def __init__(self, config: Optional[MuseTalkConfig] = None) -> None:
        self.config = config or MuseTalkConfig.from_env()

    @property
    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.config.auth_token}"}

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            r = await client.get(
                f"{self.config.base_url}/musetalk/health",
                headers=self._auth_headers,
            )
            r.raise_for_status()
            return r.json()

    async def enroll_reference(
        self,
        image_bytes: bytes,
        subject: str,
        age: Optional[int] = None,
    ) -> dict:
        """Upload reference face image (Sophie portrait) for lipsync.

        Args:
            image_bytes: PNG bytes (>=1024x1024 recommended).
            subject: identifier (free-form, passed to server as metadata).
            age: optional age metadata (currently unused, retained for future use).
        """
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            r = await client.post(
                f"{self.config.base_url}/musetalk/enroll",
                headers=self._auth_headers,
                files={"image": ("ref.png", image_bytes, "image/png")},
                data={"subject": subject},
            )
            r.raise_for_status()
            return r.json()

    def stream_url(self, subject: str, age: Optional[int] = None) -> str:
        """Return WebSocket URL for the MuseTalk stream endpoint.

        Caller must connect with `Authorization: Bearer <token>` header.
        """
        return f"{self.config.base_url.replace('https://', 'wss://')}/musetalk/stream"


__all__ = [
    "MuseTalkConfig",
    "MuseTalkClient",
]
