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

    # ===== v1.7.1 感知層 · 時間 / 天氣 / 工作狀態 =====

    @app.post("/brain/get_time_context")
    async def _get_time_context(request: Request):
        from datetime import datetime
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo("Asia/Taipei")
            now = datetime.now(tz)
        except Exception:
            now = datetime.now()
        weekday_zh = ["週一","週二","週三","週四","週五","週六","週日"][now.weekday()]
        hour = now.hour
        if hour < 5: period = "深夜"
        elif hour < 9: period = "早上"
        elif hour < 12: period = "上午"
        elif hour < 14: period = "中午"
        elif hour < 18: period = "下午"
        elif hour < 22: period = "晚上"
        else: period = "深夜"
        return {
            "ok": True,
            "now": now.strftime("%Y-%m-%d %H:%M"),
            "weekday": weekday_zh,
            "period": period,
            "hour": hour,
            "is_weekend": now.weekday() >= 5,
            "timezone": "Asia/Taipei",
        }

    @app.post("/brain/get_weather")
    async def _get_weather(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        city = "Taipei"
        if isinstance(body, dict) and body.get("city"):
            city = str(body["city"])
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"https://wttr.in/{city}?format=j1&lang=zh-tw")
                data = r.json()
                current = data.get("current_condition", [{}])[0]
                temp_c = current.get("temp_C", "?")
                feels = current.get("FeelsLikeC", "?")
                humidity = current.get("humidity", "?")
                weather_desc = current.get("lang_zh-tw", [{}])
                desc_zh = (weather_desc[0].get("value", "") if weather_desc else "") or current.get("weatherDesc", [{}])[0].get("value", "")
                wind = current.get("windspeedKmph", "?")
                return {
                    "ok": True,
                    "city": city,
                    "temp_c": temp_c,
                    "feels_like_c": feels,
                    "humidity_pct": humidity,
                    "description": desc_zh,
                    "wind_kmph": wind,
                }
        except Exception as e:
            logger.exception("[brain] get_weather fail")
            return {"ok": False, "detail": str(e)[:200]}

    @app.post("/brain/get_work_status")
    async def _get_work_status(request: Request):
        path = "/lipsync_cache/sophie_work_status.json"
        if not os.path.exists(path):
            return {
                "ok": True,
                "status_summary": "目前沒看到工作狀態紀錄 · 你可以告訴我你正在動什麼專案",
                "projects": [],
                "last_updated": None,
            }
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ok": True, **data}
        except Exception as e:
            logger.exception("[brain] get_work_status fail")
            return {"ok": False, "detail": str(e)[:200]}

    # ===== v1.7 共用記事本 · 跨裝置同步 (Voice ↔ Cowork) =====

    @app.post("/memory/shared/set")
    async def _shared_set(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)
        key = body.get("key")
        value = body.get("value")
        if not key or not isinstance(key, str):
            return JSONResponse({"ok": False, "detail": "key missing"}, status_code=400)
        # 防 path traversal
        safe_key = "".join(c for c in key if c.isalnum() or c in "_-")[:64]
        if not safe_key:
            return JSONResponse({"ok": False, "detail": "key invalid"}, status_code=400)
        path = f"/lipsync_cache/shared_{safe_key}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"key": safe_key, "value": value, "ts": time.time()}, f, ensure_ascii=False)
            return {"ok": True, "key": safe_key}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.get("/memory/shared/get/{key}")
    async def _shared_get(key: str):
        safe_key = "".join(c for c in key if c.isalnum() or c in "_-")[:64]
        path = f"/lipsync_cache/shared_{safe_key}.json"
        if not os.path.exists(path):
            return {"ok": False, "detail": "not found", "key": safe_key}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ok": True, **data}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.get("/memory/shared/list")
    async def _shared_list():
        import glob
        try:
            files = glob.glob("/lipsync_cache/shared_*.json")
            keys = [os.path.basename(f).replace("shared_", "").replace(".json", "") for f in files]
            return {"ok": True, "keys": keys, "total": len(keys)}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    # ===== v1.8.3 會議代理人模式 · 8 大專業助理能力 =====

    @app.post("/brain/start_meeting")
    async def _start_meeting(request: Request):
        """蘇菲進入會議代理模式 · 接收會議元資料 + Claude 整理會前 brief"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)

        subject = body.get("subject", "")
        goal = body.get("goal", "")
        attendees = body.get("attendees", "")
        duration_min = body.get("duration_min", 30)
        edward_position = body.get("edward_position", "")  # Edward 對議題的立場

        meeting_data = {
            "subject": subject,
            "goal": goal,
            "attendees": attendees,
            "duration_min": duration_min,
            "edward_position": edward_position,
            "started_ts": time.time(),
            "transcript": [],
            "topics_covered": [],
            "topics_pending": [],
        }

        # 寫進共用記事本 current_meeting
        try:
            with open("/lipsync_cache/shared_current_meeting.json", "w", encoding="utf-8") as f:
                json.dump({"key": "current_meeting", "value": meeting_data, "ts": time.time()}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("[brain] start_meeting save fail: %s", str(e)[:200])

        # Claude 整理會前 brief
        api_key = _resolve_anthropic_key()
        brief = ""
        if api_key:
            try:
                from anthropic import Anthropic
                cli = Anthropic(api_key=api_key)
                prompt_user = (
                    f"[會議準備]\n"
                    f"主題: {subject}\n"
                    f"目標: {goal}\n"
                    f"與會者: {attendees}\n"
                    f"預計時長: {duration_min} 分鐘\n"
                    f"Edward 立場: {edward_position}\n\n"
                    "你是蘇菲 · 即將代 Edward 出席這場會議。\n"
                    "請用 1 段 (≤ 120 字) 蘇菲口吻給 Edward 一個會前 brief：\n"
                    "1. 我已記下主題 + 目標 + 與會者\n"
                    "2. 我會怎麼引導會議 (簡述策略)\n"
                    "3. 哪些點我會特別注意 / 哪些點高風險我會說『需跟 Edward 確認』\n"
                    "結尾留個鉤子讓 Edward 補充 (譬如『你還有什麼要我注意的嗎』)"
                )
                msg = cli.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=400,
                    system="你是 Sophie · Edward 個人 AI 特助 · 即將代他出席會議 · zh-TW 自然口語",
                    messages=[{"role": "user", "content": prompt_user}],
                )
                brief = msg.content[0].text if msg.content else ""
            except Exception as e:
                logger.exception("[brain] start_meeting brief fail")
                brief = f"好 · 我記下了 · 主題 {subject} · 與會 {attendees} · {duration_min} 分鐘 · 你還有要我注意的嗎"

        return {"ok": True, "brief": brief, "meeting": meeting_data}

    @app.post("/brain/log_meeting_turn")
    async def _log_meeting_turn(request: Request):
        """會議中累積對話紀錄"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)

        speaker = body.get("speaker", "unknown")
        content = body.get("content", "")
        if not content:
            return {"ok": False, "detail": "content missing"}

        path = "/lipsync_cache/shared_current_meeting.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("value", {})
            transcript = data.get("transcript", [])
            transcript.append({"speaker": speaker, "content": content, "ts": time.time()})
            data["transcript"] = transcript
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"key": "current_meeting", "value": data, "ts": time.time()}, f, ensure_ascii=False)
            return {"ok": True, "transcript_len": len(transcript)}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.post("/brain/meeting_status")
    async def _meeting_status(request: Request):
        """會議進度 · 剩餘時間 / 已 cover 議題 / 未 cover"""
        path = "/lipsync_cache/shared_current_meeting.json"
        if not os.path.exists(path):
            return {"ok": False, "detail": "no active meeting"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("value", {})
            elapsed_sec = time.time() - data.get("started_ts", time.time())
            elapsed_min = elapsed_sec / 60
            duration_min = data.get("duration_min", 30)
            remaining_min = max(0, duration_min - elapsed_min)
            return {
                "ok": True,
                "subject": data.get("subject", ""),
                "elapsed_min": round(elapsed_min, 1),
                "remaining_min": round(remaining_min, 1),
                "duration_min": duration_min,
                "transcript_turns": len(data.get("transcript", [])),
                "topics_covered": data.get("topics_covered", []),
                "topics_pending": data.get("topics_pending", []),
                "overtime": elapsed_min > duration_min,
            }
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.post("/brain/end_meeting")
    async def _end_meeting(request: Request):
        """蘇菲結束會議 · Claude 整理 transcript → 會後正式紀錄"""
        path = "/lipsync_cache/shared_current_meeting.json"
        if not os.path.exists(path):
            return {"ok": False, "detail": "no active meeting"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("value", {})
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

        api_key = _resolve_anthropic_key()
        if not api_key:
            return {"ok": False, "detail": "anthropic key missing"}

        transcript_str = "\n".join([
            f"{t.get('speaker', '?')}: {t.get('content', '')}"
            for t in data.get("transcript", [])
        ])

        try:
            from anthropic import Anthropic
            cli = Anthropic(api_key=api_key)
            prompt_user = (
                f"[會議資訊]\n"
                f"主題: {data.get('subject', '')}\n"
                f"目標: {data.get('goal', '')}\n"
                f"與會者: {data.get('attendees', '')}\n\n"
                f"[完整對話]\n{transcript_str[:8000]}\n\n"
                "你是 Sophie · 剛剛代 Edward 出席這場會議。請整理會後紀錄："
                "\n\n## 摘要\n(3-5 句蘇菲口吻給 Edward 聽)"
                "\n\n## 重點決議\n(條列、客觀)"
                "\n\n## 待辦事項\n(誰 + 什麼 + 何時)"
                "\n\n## Edward 需確認 / 需動作\n(條列、高風險或需 Edward 拍板的事)"
                "\n\n## 下次會議建議\n(若有後續)"
            )
            msg = cli.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1500,
                system="你是 Sophie · Edward 個人 AI 特助 · 剛剛代他出席會議 · 用 zh-TW 整理會後紀錄",
                messages=[{"role": "user", "content": prompt_user}],
            )
            notes = msg.content[0].text if msg.content else ""

            # 存進 meeting archive
            archive_path = f"/lipsync_cache/shared_meeting_archive_{int(time.time())}.json"
            archive_data = {
                **data,
                "ended_ts": time.time(),
                "notes": notes,
            }
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump({"key": f"meeting_archive_{int(time.time())}", "value": archive_data, "ts": time.time()}, f, ensure_ascii=False)

            # 清掉 current_meeting
            try:
                os.remove(path)
            except Exception:
                pass

            return {"ok": True, "notes": notes, "subject": data.get("subject", "")}
        except Exception as e:
            logger.exception("[brain] end_meeting fail")
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    # ===== v1.7.6 主動聊 · 興趣學習 + 新聞分享 =====

    @app.post("/brain/news_brief")
    async def _news_brief(request: Request):
        """蘇菲拉新聞 + Edward 興趣記事本 + Claude 整理蘇菲口吻分享"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        topic = (body.get("topic") if isinstance(body, dict) else None) or "AI / 財經 / 政治 / 電影"

        # 1. 拿 Edward 興趣（從共用記事本）
        interests = []
        try:
            interests_path = "/lipsync_cache/shared_user_interests.json"
            if os.path.exists(interests_path):
                with open(interests_path, "r", encoding="utf-8") as f:
                    interests = json.load(f).get("value", {}).get("interests", [])
        except Exception:
            pass

        # 2. 用 Claude 整理一段「蘇菲分享今天的新鮮事」
        api_key = _resolve_anthropic_key()
        if not api_key:
            return {"ok": False, "detail": "anthropic key missing"}

        try:
            from anthropic import Anthropic
            cli = Anthropic(api_key=api_key)
            interests_str = (
                f"Edward 興趣：{', '.join(interests)}\n" if interests else
                "Edward 興趣：尚未紀錄、可從 AI / 財經 / 創業 / 設計 著手\n"
            )
            prompt_user = (
                interests_str
                + f"主題範圍：{topic}\n\n"
                "請以蘇菲口吻、給 Edward 1 段「今天我看到一個有趣的東西」分享。"
                "規則：\n"
                "1. ≤ 100 字 · 純口語\n"
                "2. 不要說『我看了新聞』· 改成『我看到一個事』『最近有個有趣的』\n"
                "3. 一次只分享 1 件事、不要列清單\n"
                "4. 結尾留個鉤子：「你想聽我詳細講嗎？」「你有想法嗎？」\n"
                "5. 不要編造具體事實 (公司名 / 數據)、若不確定就用『最近聽說』『有人在討論』\n"
                "6. 蘇菲第一人稱『我』+『Edward / 你』、不矯飾"
            )
            msg = cli.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                system="你是 Sophie · Edward 個人特助 + 陪伴 · zh-TW 自然口語",
                messages=[{"role": "user", "content": prompt_user}],
            )
            share = msg.content[0].text if msg.content else ""
            return {"ok": True, "share": share, "topic": topic, "interests_used": interests}
        except Exception as e:
            logger.exception("[brain] news_brief fail")
            return {"ok": False, "detail": str(e)[:200]}

    @app.post("/brain/save_interest")
    async def _save_interest(request: Request):
        """蘇菲記下 Edward 提到的興趣"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)
        new_interest = body.get("interest")
        if not new_interest or not isinstance(new_interest, str):
            return JSONResponse({"ok": False, "detail": "interest missing"}, status_code=400)

        path = "/lipsync_cache/shared_user_interests.json"
        try:
            existing = {"interests": []}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f).get("value", {"interests": []})
            interests = existing.get("interests", [])
            if new_interest not in interests:
                interests.append(new_interest)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"key": "user_interests", "value": {"interests": interests[-30:]}, "ts": time.time()}, f, ensure_ascii=False)
            return {"ok": True, "total": len(interests), "added": new_interest}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    # ===== v1.7.5 訂位代辦 · 蘇菲幫整理訂位資訊 =====

    @app.post("/brain/restaurant_booking")
    async def _restaurant_booking(request: Request):
        """蘇菲整理訂位資料 + 帶 Google 搜尋連結 + 存共用記事本"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "detail": "body must be object"}, status_code=400)

        restaurant = body.get("restaurant") or ""
        when = body.get("when") or ""
        party = body.get("party_size") or ""
        special = body.get("special_request", "") or ""

        if not restaurant:
            return JSONResponse({"ok": False, "detail": "restaurant missing"}, status_code=400)

        import urllib.parse
        search_q = f"{restaurant} 線上訂位"
        google_search = f"https://www.google.com/search?q={urllib.parse.quote(search_q)}"
        maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(restaurant)}"

        # 用 Claude 寫蘇菲口吻 brief
        api_key = _resolve_anthropic_key()
        brief = ""
        if api_key:
            try:
                from anthropic import Anthropic
                cli = Anthropic(api_key=api_key)
                prompt_user = (
                    f"[訂位請求]\n"
                    f"餐廳: {restaurant}\n"
                    f"時間: {when}\n"
                    f"人數: {party}\n"
                    f"備註: {special}\n\n"
                    "請給 Edward 1 段口頭回應、≤ 80 字、蘇菲口吻、像朋友轉述。"
                    "提示他：你會把訂位資料存進筆記、他可以從 Google 搜該餐廳訂位連結 · 或打電話。"
                    "不要說『以下幾點』類條列。"
                )
                msg = cli.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=300,
                    system="你是 Sophie · Edward 個人特助 · zh-TW 自然口語",
                    messages=[{"role": "user", "content": prompt_user}],
                )
                brief = msg.content[0].text if msg.content else ""
            except Exception as e:
                logger.exception("[brain] restaurant_booking claude fail")
                brief = f"我幫你整理了 {restaurant} 訂位資料 · Google 搜訂位連結 · 我把資料存進筆記了"

        # 存進共用記事本 (key=last_booking)
        booking_data = {
            "restaurant": restaurant,
            "when": when,
            "party_size": party,
            "special_request": special,
            "google_search": google_search,
            "maps_url": maps_url,
            "brief": brief,
            "ts": time.time(),
        }
        try:
            with open("/lipsync_cache/shared_last_booking.json", "w", encoding="utf-8") as f:
                json.dump({"key": "last_booking", "value": booking_data, "ts": time.time()}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("[brain] booking save fail: %s", str(e)[:200])

        return {
            "ok": True,
            "brief": brief,
            "restaurant": restaurant,
            "when": when,
            "party_size": party,
            "google_search": google_search,
            "maps_url": maps_url,
            "saved_to_notebook": True,
        }

    # ===== v1.7.2 晨間簡報 · 蘇菲特助級早安整合 =====

    @app.post("/brain/morning_brief")
    async def _morning_brief(request: Request):
        """整合時間 + 天氣 + 工作狀態 + 近期對話 → Claude 寫成蘇菲口吻 brief"""
        from datetime import datetime
        try:
            import zoneinfo
            now = datetime.now(zoneinfo.ZoneInfo("Asia/Taipei"))
        except Exception:
            now = datetime.now()

        # 1. 時間
        weekday_zh = ["週一","週二","週三","週四","週五","週六","週日"][now.weekday()]
        is_weekend = now.weekday() >= 5
        hour = now.hour

        # 2. 天氣
        weather_str = ""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=8) as cli:
                r = await cli.get("https://wttr.in/Taipei?format=j1&lang=zh-tw")
                w = r.json().get("current_condition", [{}])[0]
                desc_arr = w.get("lang_zh-tw", [{}])
                desc = (desc_arr[0].get("value", "") if desc_arr else "") or w.get("weatherDesc", [{}])[0].get("value", "")
                weather_str = f"台北 {w.get('temp_C','?')}°C 體感 {w.get('FeelsLikeC','?')}°C · {desc} · 濕度 {w.get('humidity','?')}%"
        except Exception:
            weather_str = "(天氣查不到)"

        # 3. 工作狀態
        work_summary = "目前沒看到工作狀態紀錄"
        try:
            ws_path = "/lipsync_cache/sophie_work_status.json"
            if os.path.exists(ws_path):
                with open(ws_path, "r", encoding="utf-8") as f:
                    ws_data = json.load(f)
                work_summary = ws_data.get("status_summary", str(ws_data)[:300])
        except Exception:
            pass

        # 4. Claude 整合成 brief (蘇菲口吻 ≤ 80 字 · 純對話、不寫條列)
        api_key = _resolve_anthropic_key()
        if not api_key:
            # graceful fallback · 沒 Claude 也能組基本 brief
            brief = f"Edward 早 · 今天{weekday_zh}{'（週末）' if is_weekend else ''} · {weather_str} · {work_summary[:80]}"
            return {"ok": True, "brief": brief, "fallback": True}

        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            prompt_user = (
                f"[時間] {now.strftime('%Y-%m-%d %H:%M')} · {weekday_zh}"
                f"{' · 週末' if is_weekend else ''}\n"
                f"[天氣] {weather_str}\n"
                f"[工作狀態] {work_summary}\n\n"
                "請把上面整理成 1 段蘇菲早安 brief、給 Edward 聽。"
                "規則：≤ 100 字 / 純口語對話 / 不要條列 / 不要說「以下幾點」/ 直接像朋友早上跟你說話。"
                "週末就放鬆一點、工作日就帶點推進感。"
                "若工作狀態空、就先寒暄 + 問 Edward『今天想動什麼』。"
            )
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                system=(
                    "你是 Sophie · Edward 個人特助。"
                    "口吻：堅定 / 樸實 / 不矯飾 / 第一人稱『我』+『Edward / 你』。"
                    "zh-TW 自然口語。"
                ),
                messages=[{"role": "user", "content": prompt_user}],
            )
            brief = msg.content[0].text if msg.content else ""
            return {"ok": True, "brief": brief, "time": now.strftime("%H:%M"), "weekday": weekday_zh}
        except Exception as e:
            logger.exception("[brain] morning_brief fail")
            # graceful fallback
            brief = f"Edward 早 · 今天{weekday_zh} · {weather_str} · 今天想動什麼？"
            return {"ok": True, "brief": brief, "fallback": True, "detail": str(e)[:200]}

    # ===== v1.8.6 跨會議記憶 + silent/active 切換 =====

    @app.post("/brain/get_contact_history")
    async def _get_contact_history(request: Request):
        """蘇菲開新會議前、先撈這個對方歷史紀錄、知道上次聊過什麼"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        contact_name = (body.get("contact_name") or "").strip()
        if not contact_name:
            return {"ok": False, "detail": "contact_name missing"}

        # 安全的檔名 (去掉路徑符號)
        safe_name = "".join(c for c in contact_name if c.isalnum() or c in "_-")[:80]
        path = f"/lipsync_cache/shared_contact_{safe_name}.json"
        if not os.path.exists(path):
            return {"ok": True, "contact_name": contact_name, "first_time": True, "history": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("value", {})
            return {
                "ok": True,
                "contact_name": contact_name,
                "first_time": False,
                "meetings_count": len(data.get("meetings", [])),
                "last_meeting_ts": data.get("last_meeting_ts"),
                "key_topics": data.get("key_topics", []),
                "pending_followups": data.get("pending_followups", []),
                "edward_notes": data.get("edward_notes", ""),
                "recent_meetings": data.get("meetings", [])[-3:],  # 最近 3 次
            }
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.post("/brain/save_contact_meeting")
    async def _save_contact_meeting(request: Request):
        """end_meeting 後把這場會議併進對方檔案 · 累積跨會議記憶"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        contact_name = (body.get("contact_name") or "").strip()
        if not contact_name:
            return {"ok": False, "detail": "contact_name missing"}

        meeting_summary = body.get("meeting_summary", "")
        key_topics = body.get("key_topics", [])
        followups = body.get("followups", [])
        ts = time.time()

        safe_name = "".join(c for c in contact_name if c.isalnum() or c in "_-")[:80]
        path = f"/lipsync_cache/shared_contact_{safe_name}.json"

        # Load existing or init
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f).get("value", {})
            except Exception:
                data = {}
        else:
            data = {}

        meetings = data.get("meetings", [])
        meetings.append({
            "ts": ts,
            "summary": meeting_summary[:2000],  # 防爆長
            "topics": key_topics,
        })
        # 累積熱門 topics (取最近 10 場、出現 > 1 次)
        all_topics = []
        for m in meetings[-10:]:
            all_topics.extend(m.get("topics", []))
        topic_freq = {}
        for t in all_topics:
            topic_freq[t] = topic_freq.get(t, 0) + 1
        hot_topics = [t for t, c in sorted(topic_freq.items(), key=lambda x: -x[1]) if c >= 2][:5]

        data["contact_name"] = contact_name
        data["meetings"] = meetings[-50:]  # 上限 50 場避免無限長
        data["key_topics"] = hot_topics
        data["pending_followups"] = (data.get("pending_followups", []) + followups)[-10:]
        data["last_meeting_ts"] = ts

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"key": f"contact_{safe_name}", "value": data, "ts": ts}, f, ensure_ascii=False)
            return {"ok": True, "contact_name": contact_name, "total_meetings": len(meetings)}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.post("/brain/set_meeting_mode")
    async def _set_meeting_mode(request: Request):
        """切換蘇菲在會議裡的 mode: silent (安靜聽) / active (主動代答) / brief (只私語 Edward)"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)
        mode = (body.get("mode") or "").strip().lower()
        if mode not in ("silent", "active", "brief"):
            return {"ok": False, "detail": "mode must be silent / active / brief"}

        path = "/lipsync_cache/shared_meeting_mode.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"key": "meeting_mode", "value": {"mode": mode, "set_ts": time.time()}, "ts": time.time()}, f, ensure_ascii=False)
            mode_desc = {
                "silent": "靜音聆聽 · 只記不講 · Edward 喚才開口",
                "active": "主動代理 · 蘇菲可開口代 Edward 講",
                "brief": "私語 brief · 蘇菲對著 Edward 耳邊 brief、不對與會者講",
            }
            return {"ok": True, "mode": mode, "description": mode_desc[mode]}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.post("/brain/get_meeting_mode")
    async def _get_meeting_mode(request: Request):
        """讀當前 mode (default silent · 保守設定)"""
        path = "/lipsync_cache/shared_meeting_mode.json"
        if not os.path.exists(path):
            return {"ok": True, "mode": "silent", "default": True}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("value", {})
            return {"ok": True, "mode": data.get("mode", "silent"), "set_ts": data.get("set_ts")}
        except Exception:
            return {"ok": True, "mode": "silent", "default": True}

    # ===== v1.8.7 需求訪談模式 =====

    @app.post("/brain/start_interview")
    async def _start_interview(request: Request):
        """訪談開始 · 蘇菲拿到 brief + 訪談大綱 + 該用哪個方法論 (JTBD / Mom Test / 5 Why)"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)

        topic = body.get("topic", "")
        hypothesis = body.get("hypothesis", "")  # Edward 想驗證的假設
        interviewee = body.get("interviewee", "")  # 受訪者 (姓名 / persona)
        method = (body.get("method") or "jtbd").lower()  # jtbd / mom_test / 5why
        duration_min = body.get("duration_min", 30)

        interview_data = {
            "topic": topic,
            "hypothesis": hypothesis,
            "interviewee": interviewee,
            "method": method,
            "duration_min": duration_min,
            "started_ts": time.time(),
            "transcript": [],
            "insights": [],
            "why_chain_depth": 0,  # 已追問到第幾層
            "bias_flags": [],
        }

        try:
            with open("/lipsync_cache/shared_current_interview.json", "w", encoding="utf-8") as f:
                json.dump({"key": "current_interview", "value": interview_data, "ts": time.time()}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("[brain] start_interview save fail: %s", str(e)[:200])

        # 訪談大綱：按方法論選 prompt
        method_prompts = {
            "jtbd": (
                "Jobs-To-Be-Done 框架 · 5 段：\n"
                "1. 當下情境 (When you... 描述觸發場景)\n"
                "2. 動機 (What were you trying to accomplish? 想達成什麼)\n"
                "3. 替代方案 (What did you try first? 之前怎麼解)\n"
                "4. 不滿意點 (What went wrong? 哪裡卡)\n"
                "5. 理想狀態 (If you had a magic wand? 完美解長怎樣)\n"
            ),
            "mom_test": (
                "Mom Test 三原則 · 跑訪談時時提醒自己：\n"
                "1. 講過去、不講未來 (Talk about their life, not your idea)\n"
                "2. 問具體事件、不問抽象意見 (Ask specifics, not generics)\n"
                "3. 多聽少講 (Talk less, listen more · 70-30 法則)\n"
                "禁問：『你會用 X 嗎』『你覺得 X 好不好』『會付錢嗎』(都是引導性 + hypothetical)\n"
                "改問：『上次遇到 X 是什麼時候、那次怎麼處理的』\n"
            ),
            "5why": (
                "5 Why 反問鏈 · 每個關鍵答案追 4-6 層 why：\n"
                "對方說『我覺得不錯』→『為什麼這樣覺得 · 具體哪裡』\n"
                "對方說『因為方便』→『為什麼方便對你重要 · 替代方案差在哪』\n"
                "對方說『因為省時間』→『省下的時間你拿去做什麼』\n"
                "...連追 4-6 層直到對方答出『真實動機』(emotional / social drive)\n"
            ),
        }
        method_prompt = method_prompts.get(method, method_prompts["jtbd"])

        api_key = _resolve_anthropic_key()
        brief = ""
        if api_key:
            try:
                from anthropic import Anthropic
                cli = Anthropic(api_key=api_key)
                prompt_user = (
                    f"[訪談準備]\n"
                    f"主題: {topic}\n"
                    f"Edward 假設: {hypothesis}\n"
                    f"受訪者: {interviewee}\n"
                    f"預計時長: {duration_min} 分鐘\n"
                    f"方法論: {method}\n\n"
                    f"方法論 cheatsheet:\n{method_prompt}\n\n"
                    "你是 Sophie · 即將代 Edward 跑這場需求訪談。\n"
                    "請用 1 段 (≤ 150 字) 蘇菲口吻給 Edward 一個訪談前 brief：\n"
                    "1. 我會怎麼開場 (破冰句、不問引導性問題)\n"
                    "2. 我會用什麼方法論套對方 (JTBD / Mom Test / 5 Why 哪幾個)\n"
                    "3. 哪些 bias 我會特別小心 (討好 / 假設 / 編造)\n"
                    "結尾問 Edward『你還有想驗證的假設嗎』"
                )
                msg = cli.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=500,
                    system="你是 Sophie · Edward 個人 AI 特助 · 即將代他跑需求訪談 · zh-TW 自然口語",
                    messages=[{"role": "user", "content": prompt_user}],
                )
                brief = msg.content[0].text if msg.content else ""
            except Exception as e:
                logger.exception("[brain] start_interview brief fail")
                brief = f"訪談準備好了 · 主題 {topic} · 用 {method} 跑 · 你還有想驗證的假設嗎"

        return {"ok": True, "brief": brief, "method_cheatsheet": method_prompt, "interview": interview_data}

    @app.post("/brain/log_interview_insight")
    async def _log_interview_insight(request: Request):
        """訪談中蘇菲捕到 insight · 即時 flag (痛點 / 動機 / bias / 假設驗證)"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "detail": "body parse fail"}, status_code=400)

        insight_type = (body.get("type") or "").lower()  # pain / motivation / bias / verified / contradicted
        content = body.get("content", "")
        speaker = body.get("speaker", "interviewee")

        path = "/lipsync_cache/shared_current_interview.json"
        if not os.path.exists(path):
            return {"ok": False, "detail": "no active interview"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("value", {})
            insights = data.get("insights", [])
            insights.append({
                "type": insight_type,
                "content": content,
                "speaker": speaker,
                "ts": time.time(),
            })
            data["insights"] = insights
            if insight_type == "bias":
                data["bias_flags"] = data.get("bias_flags", []) + [content[:120]]
            # transcript 也存
            transcript = data.get("transcript", [])
            transcript.append({"speaker": speaker, "content": content, "ts": time.time()})
            data["transcript"] = transcript

            with open(path, "w", encoding="utf-8") as f:
                json.dump({"key": "current_interview", "value": data, "ts": time.time()}, f, ensure_ascii=False)
            return {"ok": True, "insights_count": len(insights), "bias_count": len(data.get("bias_flags", []))}
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    @app.post("/brain/end_interview")
    async def _end_interview(request: Request):
        """訪談結束 · Claude 整理：痛點 / 動機 / 假設驗證結果 / 跨訪談 insight cluster"""
        path = "/lipsync_cache/shared_current_interview.json"
        if not os.path.exists(path):
            return {"ok": False, "detail": "no active interview"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("value", {})
        except Exception as e:
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

        api_key = _resolve_anthropic_key()
        if not api_key:
            return {"ok": False, "detail": "anthropic key missing"}

        transcript_str = "\n".join([
            f"{t.get('speaker', '?')}: {t.get('content', '')}"
            for t in data.get("transcript", [])
        ])
        insights_str = "\n".join([
            f"[{i.get('type', '?')}] {i.get('content', '')}"
            for i in data.get("insights", [])
        ])

        try:
            from anthropic import Anthropic
            cli = Anthropic(api_key=api_key)
            prompt_user = (
                f"[訪談資訊]\n"
                f"主題: {data.get('topic', '')}\n"
                f"Edward 假設: {data.get('hypothesis', '')}\n"
                f"受訪者: {data.get('interviewee', '')}\n"
                f"方法論: {data.get('method', '')}\n\n"
                f"[即時捕到的 insights]\n{insights_str[:3000]}\n\n"
                f"[完整對話]\n{transcript_str[:6000]}\n\n"
                "你是 Sophie · 剛代 Edward 跑完這場需求訪談。請整理：\n\n"
                "## 摘要\n(3-5 句蘇菲口吻給 Edward 聽)\n\n"
                "## 核心痛點 (排序、最痛在前)\n(每條：痛點 + 出現幾次 + 對方原話)\n\n"
                "## 真實動機 (5 Why 追到底的 emotional / social drive)\n\n"
                "## Edward 假設驗證結果\n- 假設『X』→ 驗證 / 反駁 / 部分驗證 + 證據\n\n"
                "## 反例 / 意外發現\n(對方說了什麼出乎 Edward 預期的)\n\n"
                "## bias 警告 (討好 / 假設 / 編造的回答 · 別當真)\n\n"
                "## 下一步建議\n(這場學到什麼 + 下次該問誰 / 問什麼)"
            )
            msg = cli.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                system="你是 Sophie · Edward 個人 AI 特助 · 剛跑完需求訪談 · 用 zh-TW 整理研究 insight",
                messages=[{"role": "user", "content": prompt_user}],
            )
            notes = msg.content[0].text if msg.content else ""

            # 存進 interview archive
            archive_path = f"/lipsync_cache/shared_interview_archive_{int(time.time())}.json"
            archive_data = {
                **data,
                "ended_ts": time.time(),
                "notes": notes,
            }
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump({"key": f"interview_archive_{int(time.time())}", "value": archive_data, "ts": time.time()}, f, ensure_ascii=False)

            try:
                os.remove(path)
            except Exception:
                pass

            return {"ok": True, "notes": notes, "topic": data.get("topic", ""), "insights_count": len(data.get("insights", []))}
        except Exception as e:
            logger.exception("[brain] end_interview fail")
            return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)
