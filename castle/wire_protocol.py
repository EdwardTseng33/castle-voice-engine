# castle-voice-engine — Copyright (c) 2026 Edward / BeyondPath
# Built on PersonaPlex (NVIDIA, NOML) and Moshi (Kyutai, MIT)
# castle/wire_protocol.py — JSON envelope + binary frame schema for the Castle Voice Engine WebSocket.

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional

EnvelopeType = Literal[
    "hello",
    "connected",
    "user_text",
    "switch_persona",
    "goodbye",
    "state_change",
    "partial_transcript",
    "final_transcript",
    "audio_chunk_meta",
    "error",
]

# --- Outbound (server -> client) helpers ---

def envelope(type_: EnvelopeType, **fields: Any) -> str:
    payload: dict[str, Any] = {"type": type_, "ts": int(time.time() * 1000)}
    payload.update({k: v for k, v in fields.items() if v is not None})
    return json.dumps(payload, ensure_ascii=False)

def connected(session_id: str, persona: str, voice_preset_id: str = "NATF1", engine: str = "castle-voice-engine") -> str:
    return envelope("connected", sessionId=session_id, persona=persona, voicePresetId=voice_preset_id, engine=engine)

def state_change(from_state: str, to_state: str) -> str:
    return envelope("state_change", **{"from": from_state, "to": to_state})

def partial_transcript(text: str, source: Literal["user", "agent"] = "user") -> str:
    return envelope("partial_transcript", text=text, source=source)

def final_transcript(text: str, source: Literal["user", "agent"] = "user") -> str:
    return envelope("final_transcript", text=text, source=source)

def audio_chunk_meta(seq: int, byte_len: int, fmt: str = "opus") -> str:
    return envelope("audio_chunk_meta", seq=seq, bytes=byte_len, format=fmt)

def error(message: str, code: Optional[str] = None) -> str:
    return envelope("error", message=message, code=code)

# --- Inbound (client -> server) parsing ---

@dataclass
class Inbound:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

def parse_inbound(raw: str) -> Inbound:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid envelope: {e}")
    if not isinstance(obj, dict) or "type" not in obj:
        raise ValueError("envelope missing 'type'")
    return Inbound(type=str(obj["type"]), data=obj)

# --- Persona registry resolver helper ---

def resolve_voice_preset(persona_yaml: dict[str, Any], requested: Optional[str] = None) -> str:
    if requested:
        return requested
    return persona_yaml.get("voice", {}).get("preset_id", "NATF1")

__all__ = [
    "EnvelopeType",
    "envelope",
    "connected",
    "state_change",
    "partial_transcript",
    "final_transcript",
    "audio_chunk_meta",
    "error",
    "Inbound",
    "parse_inbound",
    "resolve_voice_preset",
]
