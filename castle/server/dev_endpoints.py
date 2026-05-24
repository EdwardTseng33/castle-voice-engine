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

# dev bypass token · 沙利曼 Tier B Seg 1 P0 修補
# 1) token 從 Modal secret env 拉 · 不寫死 in code (舊 token 已 rotate · git history 在 Edward 端處理)
# 2) DEV_BYPASS_ENABLED env 真守 · prod env 不設 = endpoint 完全失能 (縱深防禦)
# 3) HEADER 名 export 給 app.py middleware / cookie set 副作用 用

DEV_BYPASS_HEADER = "X-Castle-Dev-Bypass"

_DEV_TOKEN = os.environ.get("CASTLE_DEV_BYPASS_TOKEN", "").strip()
_DEV_ENABLED_ENV = os.environ.get("DEV_BYPASS_ENABLED", "").strip()

# 雙守：DEV_BYPASS_ENABLED=1 AND token 非空 · 缺一即失能
_DEV_EXPLICITLY_ENABLED = (_DEV_ENABLED_ENV == "1") and bool(_DEV_TOKEN)


def _check_dev_bypass(request: Request) -> Optional[JSONResponse]:
    """驗 dev bypass header · 回 None 表示通過 · 回 JSONResponse 表示擋住.

    沙利曼 Tier B Seg 1 P0 修補：
      - 第一道 gate：若 DEV_BYPASS_ENABLED env 未設 = 整組 dev 失能 · 回 404 (不洩露 endpoint 存在)
      - 第二道 gate：header token compare_digest 比對 (constant-time)
      - prod 預設未設 DEV_BYPASS_ENABLED → 永遠拿不到 / dev/* 任何回應
    """
    # Gate 1 · env 未啟用 = 整組失能 · 404 不洩露
    if not _DEV_EXPLICITLY_ENABLED:
        return JSONResponse(
            {"ok": False, "detail": "not found"},
            status_code=404,
        )

    # Gate 2 · header token
    token = request.headers.get(DEV_BYPASS_HEADER, "").strip()
    if not token or not secrets.compare_digest(token, _DEV_TOKEN):
        return JSONResponse(
            {"ok": False, "detail": "dev bypass token required · use " + DEV_BYPASS_HEADER + " header"},
            status_code=403,
        )
    return None


def check_dev_bypass(request: Request) -> Optional[JSONResponse]:
    """Public alias · app.py / middleware 用 · 同 _check_dev_bypass 雙守邏輯.

    回 None = 此請求帶有效 dev bypass + DEV_BYPASS_ENABLED=1 · caller 可繼續處理 (含 set cookie 副作用).
    回 JSONResponse = 擋住 (404 / 403) · caller 不要動作 (依然回 None 給 caller, caller 自己判).

    使用：caller 只關心「這請求是否合法 dev bypass」, 不需要直接 return JSONResponse.
        -> 對外提供 bool 版本 is_valid_dev_bypass(request) 更乾淨.
    """
    return _check_dev_bypass(request)


def is_valid_dev_bypass(request: Request) -> bool:
    """Bool 版本 · 給 app.py /auth/whoami 判 dev bypass 副作用.

    True 才允許 mint dev cookie · 缺 env / 缺 token / token 錯 全部 False.
    """
    if not _DEV_EXPLICITLY_ENABLED:
        return False
    token = request.headers.get(DEV_BYPASS_HEADER, "").strip()
    if not token:
        return False
    try:
        return secrets.compare_digest(token, _DEV_TOKEN)
    except Exception:
        return False


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
    """掛載 /dev/* routes · 沙利曼 Tier B Seg 1 P0 修補：

    第三道 gate (縱深防禦)：若 DEV_BYPASS_ENABLED != "1" 或 token 未配置 = 整組 route 不掛載
    prod 環境 secret 不設 → route 根本不存在 → 連 404 都拿不到 (真正 "prod 等於沒這條路")
    """
    if not _DEV_EXPLICITLY_ENABLED:
        # prod / 未配置 = 完全不掛載 · 雙重保險 (env gate + route 不存在)
        try:
            import logging as _lg
            _lg.getLogger(__name__).info("[dev_endpoints] DEV_BYPASS_ENABLED != 1 or token empty · /dev/* routes NOT attached")
        except Exception:
            pass
        return

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
