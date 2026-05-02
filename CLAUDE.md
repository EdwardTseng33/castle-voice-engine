# castle-voice-engine — Claude session context

This file is auto-loaded by Claude Code at session start. Read it before proposing changes.

## What this repo is

Real-time voice runtime for the **Sophie** (zh-TW) and **Lily** (en) personas.
Deployed on Modal. WebSocket `/voice` endpoint, persona registry under
`castle/personas/*.yaml`.

Voice backend has shifted from PersonaPlex (NVIDIA NOML) → OpenAI Realtime API
as of v0.1.5 (`app.py:4`). PersonaPlex stub kept on disk as archive but no
longer attached to running app.

## Castle 7-agent team

The Sophie persona references a **7-person castle subagent system** for role
boundaries. Full division of labor lives in **`castle/TEAM.md`** — read it
before touching anything that crosses agent boundaries (hand-off rules,
persona prompts, governance).

Quick reference (full table in `castle/TEAM.md`):

- 霍爾 (Howl) · CPO — product vision, wire protocol
- 卡西法 (Calcifer) · CTO — deploy, model selection, pre-deploy risk
- 女巫 (Witch) · CDO — data / design / aesthetics
- 蕪菁頭 (Turnip) · 用戶代表 — user-side pressure testing
- 馬魯克 (Markl) · PM — execution, versioning
- 蘇曼納 (Suliman) · 治理 — NOML compliance, auth, PII
- 蘇菲 (Sophie) · COO+CFO — emotional layer (sole owner), cross-team coord

## Working norms

- **Persona changes**: edit YAML under `castle/personas/`, keep the
  `attribution:` block intact (NOML requirement).
- **Hand-off rules**: documented in `castle/TEAM.md` and mirrored in
  `sophie.yaml` prompt — keep them in sync.
- **Branch convention**: develop on `claude/<topic>-<suffix>`, push, open
  draft PR.
- **Auth**: `CVE_AUTH_TOKEN` env var; dev mode bypasses if unset
  (`engine_server.py:42`).
- **Single-tenant lock**: PersonaPlex path requires one session per server
  (`engine_server.py:32`). OpenAI Realtime path has no such constraint.

## Don't

- Don't add the castle team members as `castle/personas/*.yaml` without
  asking — the 7-person system is a team-of-developers metaphor, not
  necessarily 7 voice products.
- Don't drop NOML attribution from any persona file.
- Don't merge PRs that change hand-off rules without updating both
  `castle/TEAM.md` and the relevant persona prompt.
