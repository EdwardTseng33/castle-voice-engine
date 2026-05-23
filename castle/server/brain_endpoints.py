"""castle/server/brain_endpoints.py · v1.6.0 Brain Layer

Edward 5/23 拍板 B 版本 (雙腦混合):
- OpenAI Realtime 即時對話保留 (蘇菲講話即時感)
- OpenAI 不演「思考」· 它變「轉接員」
- 短問題 → OpenAI 直接答
- 需要深度 / 派工 → 派工到 Brain layer

3 個接口:
- POST /brain/ask_claude · 真接 Anthropic Claude API · 深度問答
- POST /brain/dispatch_howl · 派 Hub Howl + Codex (v1.6.3 接 Hub API · MVP queue)
- POST /brain/dispatch_code · 派 Claude Code 蘇菲 (Edward 端 Cowork · MVP queue)
"""

from __future__ import annotations
import os
import json
import time
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _resolve_anthropic_key():
    """Modal Secret env var 名不一定是 ANTHROPIC_API_KEY · 試 4 個常見命名"""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "anthropic_key", "ANTHROPIC"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return None


def attach_brain_routes(app):
    """Mount brain routes onto FastAPI app.

    Routes (all auth-gated via middleware · cookie required):
        POST /brain/ask_claude     · {question, context?} → {ok, answer}
        POST /brain/dispatch_howl  · {task, priority?}    → {ok, ack, status}
        POST /brain/dispatch_code  · {task}               → {ok, ack, status}
        GET  /brain/health
    """

    @app.post("/brain/ask_claude")
    async def _ask_claude(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)
        question = body.get("question")
        context = body.get("context", "")
        if not question or not isinstance(question, str):
            return JSONResponse({"ok": False, "detail": "question missing"}, status_code=400)

        api_key = _resolve_anthropic_key()
        if not api_key:
            return JSONResponse({"ok": False, "detail": "anthropic key missing", "answer": ""}, status_code=200)

        try:
            from anthropic import Anthropic
        except ImportError:
            return JSONResponse({"ok": False, "detail": "anthropic sdk missing", "answer": ""}, status_code=200)

        try:
            client = Anthropic(api_key=api_key)
            # 用 Sonnet · 速度 + 品質平衡 (Haiku 太短不夠深 · Opus 太貴)
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500,
                system=(
                    "你是 Sophie · Edward 的個人 AI 蘇菲的深度大腦。"
                    "Edward 透過 Voice Path 蘇菲問你一個需要深度思考的問題。"
                    "請用蘇菲口吻：堅定 / 樸實 / 不矯飾 / 第一人稱『我』+『Edward / 你』。"
                    "回應規則:"
                    "1. 簡短有重點 · 不超過 120 字 (語音對話、不寫長文)。"
                    "2. zh-TW 自然口語、不要 bullet point。"
                    "3. 直接給答案、不要前綴『讓我想想』之類。"
                    "4. 若需要更多上下文才能答、就直接說「我需要你補充 X」。"
                ),
                messages=[
                    {"role": "user", "content": (
                        (f"[上下文]\n{context}\n\n" if context else "")
                        + f"[Edward 問]\n{question}"
                    )}
                ]
            )
            answer = msg.content[0].text if msg.content else ""
            logger.info("[brain] ask_claude OK · q=%s · a=%s", question[:50], answer[:50])
            return JSONResponse({"ok": True, "answer": answer})
        except Exception as e:
            logger.exception("[brain] ask_claude fail")
            return JSONResponse(
                {"ok": False, "detail": str(e)[:300], "answer": "我大腦現在有點卡 · 等下再問我"},
                status_code=200,
            )

    @app.post("/brain/dispatch_howl")
    async def _dispatch_howl(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)
        task = body.get("task")
        priority = body.get("priority", "normal")
        if not task or not isinstance(task, str):
            return JSONResponse({"ok": False, "detail": "task missing"}, status_code=400)

        # MVP v1.6.1: 寫進 queue file (Modal Volume) · Hub Howl 端 v1.6.3 加 watcher
        # 之後 v1.6.3 改成直接 HTTP call Hub task queue API
        log_path = "/lipsync_cache/dispatch_howl_queue.jsonl"
        try:
            entry = {"task": task, "priority": priority, "ts": time.time(), "source": "voice_path"}
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("[brain] dispatch_howl write fail: %s", str(e)[:200])

        ack = f"好 · 我跟霍爾說『{task}』· 他結果好了會告訴我 · 我再轉給你"
        logger.info("[brain] dispatch_howl: %s", task[:60])
        return JSONResponse({
            "ok": True,
            "ack": ack,
            "status": "queued_to_howl",
            "task": task,
        })

    @app.post("/brain/dispatch_code")
    async def _dispatch_code(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)
        task = body.get("task")
        if not task or not isinstance(task, str):
            return JSONResponse({"ok": False, "detail": "task missing"}, status_code=400)

        # MVP v1.6.1: queue file · Edward 端 Cowork Claude Code 加 watcher
        log_path = "/lipsync_cache/dispatch_code_queue.jsonl"
        try:
            entry = {"task": task, "ts": time.time(), "source": "voice_path"}
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("[brain] dispatch_code write fail: %s", str(e)[:200])

        ack = f"好 · 我跟 Claude 蘇菲說『{task}』· 她做完會告訴你"
        logger.info("[brain] dispatch_code: %s", task[:60])
        return JSONResponse({
            "ok": True,
            "ack": ack,
            "status": "queued_to_claude_code",
            "task": task,
        })

    @app.get("/brain/health")
    async def _brain_health():
        return {
            "ok": True,
            "anthropic_key": bool(_resolve_anthropic_key()),
            "model": "claude-sonnet-4-5",
        }
