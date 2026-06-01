# Sophie Persona Director Plan

## Goal

Make Sophie feel like a real private assistant, not a chatbot skin, while keeping OpenAI Realtime latency stable.

The Director sits between:

- OpenAI Realtime: fast audio, turn taking, short preambles
- Claude / castle brain tools: deep work, risk review, task execution
- Avatar runtime: visual state, expression, motion, self-view policy

## Rule

Realtime should not wait on Claude for every emotional micro-moment. Claude is the deep brain. The Director decides when to stay fast and when to route deep.

## Implemented

- `GET /director/status`
- `POST /director/decide`
- Realtime instruction contract appended in `/sdp` header instructions
- Frontend calls Director on call start, user transcript, tool wait, tool result, and call end
- AvatarCompositor receives `speech_state` intents from Director decisions

## State Map

- `idle`: low-energy idle loop
- `listening`: attentive listening
- `private_care`: warm, soft, fast-lane response
- `work_focus`: deep lane, focused avatar state
- `waiting`: tool/Claude wait state
- `high_risk`: restrained mode, intimacy lowered, confirmation required

## Product Guardrails

- High-risk topics lower intimacy to 0.
- Private-care mode can be warm, but must not fake a real-world romantic relationship.
- Work mode must return result, next step, artifact/blocker.
- Waiting mode should use short preambles only; no filler monologues.
- Director logic must remain deterministic and cheap enough to call often.

## Verify

```powershell
python -m unittest tests.test_persona_director
python -m py_compile app.py castle\server\realtime_endpoints.py castle\server\persona_director.py
```

Runtime checks:

- `/director/status`
- `/director/decide`
- `/static/index.html?diag=wake`
- one real work request routes to deep lane
- one private-care turn stays in fast lane
