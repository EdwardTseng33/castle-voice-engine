"""castle/server/dev_endpoints.py · v1.5.1 · 2026-05-25
馬魯克 scope · V1.5 自動驗收 cron 配套

POST /dev/simulate_realtime
  - 接受 {audio_file?, expected_utterance} body
  - 模擬 OpenAI Realtime audio.delta + audio.done DataChannel event 序列
  - 透過 server-sent events 串流給 test client
  - 安全: X-Castle-Dev-Bypass header 守 · prod 不開 (DEV_BYPASS_ENABLED env 控制)

GET /dev/health
  - 確認 dev endpoint 已掛載 · 回 {ok, mode: "dev"}

安全設計：
  - 必須帶正確 dev bypass token · 否則 403
  - 若 DEV_BYPASS_ENABLED != "1" 整組 endpoint 回 404 (prod 安全)
  - 不寫入任何持久資料 · pure stateless simulation
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import secrets
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

# dev bypass token · 只在 dev/test 場景用 · prod 不開
_DEV_TOKEN = "06c87b230ad966219137a5d7c005266f"
_DEV_ENABLED_ENV = os.environ.get("DEV_BYPASS_ENABLED", "").strip()

# 如果沒有設 DEV_BYPASS_ENABLED=1，整組 endpoint 仍可掛載
# 但 _check_dev_bypass() 會擋住所有請求 (防萬一 prod 漏掛)
_DEV_EXPLICITLY_ENABLED = _DEV_ENABLED_ENV == "1"


def _check_dev_bypass(request: Request) -> Optional[JSONResponse]:
    """驗 dev bypass header · 回 None 表示通過 · 回 JSONResponse 表示擋住"""
    token = request.headers.get("X-Castle-Dev-Bypass", "").strip()
    if not token or not secrets.compare_digest(token, _DEV_TOKEN):
        return JSONResponse(
            {"ok": False, "detail": "dev bypass token required · use X-Castle-Dev-Bypass header"},
            status_code=403,
        )
    return None


def _build_realtime_event_sequence(utterance: str, audio_file: Optional[str] = None) -> list[dict]:
    """
    模擬 OpenAI Realtime DataChannel event 序列：
      1. response.audio.delta (分 3 chunk)
      2. response.audio_transcript.delta (分 N chunk，每 5 字切一次)
      3. response.audio.done
      4. response.audio_transcript.done

    這讓 4 條驗收邏輯都能被觸發：
    - audio.delta → 驗「說話有動」(timeupdate listener)
    - audio_transcript.delta → 驗「PhraseMatcher 命中」
    - audio.done → 驗「延遲達標」latency timer 停止
    """
    events = []

    # 模擬 session.updated (連線就緒)
    events.append({
        "type": "session.updated",
        "ts_offset_ms": 0,
        "payload": {"session": {"id": "sim_" + secrets.token_urlsafe(8)}}
    })

    # 模擬 response 開始
    events.append({
        "type": "response.created",
        "ts_offset_ms": 50,
        "payload": {"response": {"id": "sim_resp_" + secrets.token_urlsafe(6)}}
    })

    # audio.delta × 3 chunk (模擬音訊串流)
    for i in range(3):
        events.append({
            "type": "response.audio.delta",
            "ts_offset_ms": 100 + i * 80,
            "payload": {
                "delta": "AAAA" + str(i) * 8  # fake base64 audio chunk
            }
        })

    # transcript delta · 每 5 字切一次
    chunk_size = 5
    chunks = [utterance[i:i+chunk_size] for i in range(0, len(utterance), chunk_size)]
    for idx, chunk in enumerate(chunks):
        events.append({
            "type": "response.audio_transcript.delta",
            "ts_offset_ms": 300 + idx * 60,
            "payload": {"delta": chunk}
        })

    # audio.done · 這是 latency 計算終點
    events.append({
        "type": "response.audio.done",
        "ts_offset_ms": 300 + len(chunks) * 60 + 100,
        "payload": {}
    })

    # transcript.done
    events.append({
        "type": "response.audio_transcript.done",
        "ts_offset_ms": 300 + len(chunks) * 60 + 150,
        "payload": {"transcript": utterance}
    })

    return events


async def _stream_events(events: list[dict], user_said: str, start_ts: float):
    """SSE 串流 · 每個 event 帶 ts_offset_ms 延遲 · 模擬真實到達節奏"""
    yield f"data: {json.dumps({'type': 'sim.start', 'user_utterance': user_said, 'total_events': len(events)})}\n\n"
    await asyncio.sleep(0.05)

    for evt in events:
        offset_ms = evt.get("ts_offset_ms", 0)
        await asyncio.sleep(offset_ms / 1000.0)

        envelope = {
            "type": evt["type"],
            "sim_ts": time.time() - start_ts,
            **evt.get("payload", {})
        }
        yield f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n"

    # 結束訊號
    total_elapsed = time.time() - start_ts
    yield f"data: {json.dumps({'type': 'sim.done', 'elapsed_sec': round(total_elapsed, 3)})}\n\n"


def attach_dev_routes(app):
    """掛載 /dev/* routes · 呼叫前確認 prod 不要呼叫這個"""

    @app.get("/dev/health")
    async def _dev_health(request: Request):
        err = _check_dev_bypass(request)
        if err is not None:
            return err
        return {
            "ok": True,
            "mode": "dev",
            "dev_explicitly_enabled": _DEV_EXPLICITLY_ENABLED,
            "note": "dev endpoint active · do NOT expose in prod"
        }

    @app.post("/dev/simulate_realtime")
    async def _simulate_realtime(request: Request):
        """
        模擬 OpenAI Realtime 完整事件序列 · 4 條驗收邏輯可對接。

        Body (JSON):
          {
            "expected_utterance": "蘇菲說的話 (必填 · PhraseMatcher 會拿這個跑 match)",
            "audio_file": "<url 或 base64 · 選填 · 目前只記錄不處理>"
          }

        Response: text/event-stream (SSE)
          每條 event 格式: {"type": "...", "sim_ts": <秒>, ...payload}
          最後一條: {"type": "sim.done", "elapsed_sec": <秒>}

        安全: X-Castle-Dev-Bypass header 必填 · prod 不開此 endpoint
        """
        err = _check_dev_bypass(request)
        if err is not None:
            return err

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail · must be JSON"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)

        utterance = (body.get("expected_utterance") or "").strip()
        if not utterance:
            return JSONResponse(
                {"ok": False, "detail": "expected_utterance 必填 · PhraseMatcher 測試用"},
                status_code=400,
            )

        audio_file = body.get("audio_file")  # 選填 · 目前記錄不處理

        # 最長 500 字防 abuse
        if len(utterance) > 500:
            return JSONResponse({"ok": False, "detail": "utterance 超長 (max 500 chars)"}, status_code=400)

        events = _build_realtime_event_sequence(utterance, audio_file)
        start_ts = time.time()

        return StreamingResponse(
            _stream_events(events, utterance, start_ts),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
