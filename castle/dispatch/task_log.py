# castle-voice-engine - castle/dispatch/task_log.py
# (c) 2026 Edward / BeyondPath
#
# 跨 session 派工紀錄 · jsonl 持久化
# Voice Path v2.0 Phase 2 後半段
#
# 用 jsonl 不用 sqlite/db 因為:
#   - PoC 階段、量小 (< 1000 events / 月估)
#   - 易讀易 grep
#   - 未來接 castle-ai-system events/ 或 Hub task queue 直接 stream
#
# 隱私守則 (對應 security-architecture-checklist.md):
#   - 5.1 不主動收集 PII: brief / context 是 Edward 自己講的、不另外抓
#   - 5.3 不存原始語音 / 視訊 frame
#   - 7.1 audit log: 寫進 events/<date>.jsonl 跨 session 可查
#   - 不上雲 (本機 + Modal volume) · ADR-018 100% 不出 Edward 機器一條
#
# 未來升級點:
#   - 接 castle-ai-system castle/.claude/events/ 主流
#   - 接 Hub task queue (霍爾 Hub 端 review-queue.md)

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Modal 上跑時用 /tmp (ephemeral)、本機跑時用 castle-voice-engine 旁的 events/
# 未來該掛 Modal Volume (mvr) 做持久化、但 PoC 階段不必
_LOG_DIR_ENV = os.environ.get("CVE_DISPATCH_LOG_DIR", "").strip()
if _LOG_DIR_ENV:
    LOG_DIR = Path(_LOG_DIR_ENV)
else:
    # default: 同 repo 旁 events/dispatch/
    LOG_DIR = Path(__file__).resolve().parent.parent.parent / "events" / "dispatch"


def _ensure_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _today_log_path() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _ensure_dir() / f"{today}.jsonl"


def log_dispatch_event(
    member: str,
    brief: str,
    context: str = "",
    response: str = "",
    latency_ms: int = 0,
    session_id: str = "",
    status: str = "completed",
) -> dict[str, Any]:
    """
    Append a dispatch event to today's jsonl.

    Returns the event dict (含 generated event_id + ts).
    """
    event = {
        "event_id": f"disp_{int(time.time() * 1000)}",
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or "anonymous",
        "member": member,
        "brief": brief,
        "context": context,
        "response": response,
        "latency_ms": latency_ms,
        "status": status,  # completed / failed / pending
    }
    path = _today_log_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def recent_dispatches(
    limit: int = 5,
    member_filter: str | None = None,
    days_back: int = 7,
) -> list[dict[str, Any]]:
    """
    讀最近 N 天的 dispatch jsonl、過濾 + 倒序回最近 limit 筆.
    """
    _ensure_dir()
    out: list[dict[str, Any]] = []

    # 倒序掃過去 N 天 (今天 → 昨天 → ...)
    for offset in range(days_back):
        from datetime import timedelta
        day = datetime.now(timezone.utc) - timedelta(days=offset)
        path = LOG_DIR / f"{day.strftime('%Y-%m-%d')}.jsonl"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            day_events: list[dict[str, Any]] = []
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if member_filter and ev.get("member", "").lower() != member_filter.lower():
                    continue
                day_events.append(ev)
        # 同一天內維持 append order、後面的 day 在前
        # (今天 events 最後 append、所以最後一筆是最新)
        # 倒序所以今天最新在 day_events[-1]、要先把今天事件倒過來再 extend
        out.extend(reversed(day_events))
        if len(out) >= limit:
            break

    return out[:limit]
