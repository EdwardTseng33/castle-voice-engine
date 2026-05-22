# castle-voice-engine

> This project (castle-voice-engine) is built on **NVIDIA PersonaPlex 7B**,
> released under the **NVIDIA Open Model License (NOML)**, and on **Kyutai Moshi**
> (MIT). All modifications by Edward / BeyondPath. See `LICENSE.NOML` for terms.

## Talking-head module (v0.7+)

This project uses **MuseTalk v1.5** (Lyra Lab, Tencent Music Entertainment)
under the **MIT License** for real-time lipsync.

Dependencies:
- OpenAI Whisper (MIT)
- IDEA-Research DWPose (Apache-2.0)
- ft-mse-vae (CreativeML Open RAIL-M · Track B audit required for commercial use)
- S3FD (license verification pending — see `docs/v0.7-trust-audit-suliman.md`)

Reference: https://github.com/TMElyralab/MuseTalk

Real-time voice runtime that powers the Sophie persona inside `project-sophie`
(Moving Castle). Designed to:

- run on Modal A10G with scale-to-zero (cold-start ≈ 30s, warm RTT < 250ms)
- expose a single WebSocket `/voice` endpoint with JSON control + binary Opus frames
- swap personas at runtime via YAML registry (`castle/personas/*.yaml`)
- enforce single-tenant inference (PersonaPlex requires one session per server)

## Layout

```
castle-voice-engine/
├── app.py                    # Modal deploy entrypoint
├── requirements.txt          # Python runtime deps (FastAPI, websockets, torch, …)
├── LICENSE.NOML              # NOML text + 4 attribution snippets (paste full NOML before release)
├── README.md                 # this file
└── castle/
    ├── wire_protocol.py      # JSON envelope + binary frame helpers
    ├── personas/
    │   └── sophie.yaml       # default persona (others drop in alongside)
    └── server/
        └── engine_server.py  # FastAPI + WebSocket app, persona registry, single-tenant lock
```

## Quick start (local dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export CVE_AUTH_TOKEN=devtoken   # omit to disable auth (dev-only)
uvicorn castle.server.engine_server:app --host 127.0.0.1 --port 7878
# probe:
curl http://127.0.0.1:7878/health
```

## Wire protocol summary

```
client -> server  : { type: "hello",        persona: "sophie", voicePresetId: "NATF1" }
client -> server  : { type: "user_text",    text: "..." }
client -> server  : { type: "switch_persona", persona: "<name>" }
client -> server  : { type: "goodbye" }
client -> server  : <binary Opus frame>     // mic chunk

server -> client  : { type: "connected",          sessionId, persona, voicePresetId, engine }
server -> client  : { type: "state_change",       from, to, ts }
server -> client  : { type: "partial_transcript", text, source: "user"|"agent", ts }
server -> client  : { type: "final_transcript",   text, source, ts }
server -> client  : { type: "audio_chunk_meta",   seq, bytes, format: "opus" }
server -> client  : <binary Opus frame>           // synthesized voice
server -> client  : { type: "error",              message, code? }
```

Full schema: see `castle/wire_protocol.py`.

## Deploy to Modal

```bash
modal token set --token-id ... --token-secret ...
modal secret create cve-auth CVE_AUTH_TOKEN=$(openssl rand -hex 32)
modal deploy app.py
# -> ws://<deployment>.modal.run/voice  (use wss:// in browsers)
```

## Acknowledgements

- **NVIDIA PersonaPlex** team — base persona-aware voice model (NOML)
- **Kyutai Labs / Moshi** — real-time audio streaming runtime (MIT)
- **Edward / BeyondPath** — castle-voice-engine wrapping, persona registry, deploy adapters

## License

Castle Voice Engine code (this repo's wrappers, registry, deploy adapters) is © 2026
Edward / BeyondPath, released under the NVIDIA Open Model License (NOML) per the
derivative-work clause inherited from PersonaPlex. See `LICENSE.NOML` for full terms
and required attribution placements.
