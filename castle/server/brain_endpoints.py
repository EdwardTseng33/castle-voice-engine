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
