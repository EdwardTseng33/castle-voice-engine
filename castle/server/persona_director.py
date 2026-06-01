"""Persona Director for Sophie realtime sessions.

The Director is a small deterministic layer between OpenAI Realtime, Claude,
and the avatar runtime. It keeps the voice fast while routing deeper work only
when needed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


DirectorState = Literal[
    "idle",
    "listening",
    "thinking",
    "speaking",
    "private_care",
    "work_focus",
    "high_risk",
    "waiting",
]


HIGH_RISK_TERMS = (
    "付款",
    "匯款",
    "交易",
    "買股票",
    "賣股票",
    "刪除",
    "delete",
    "合約",
    "法律",
    "密碼",
    "api key",
    "token",
    "發送給客戶",
    "對外承諾",
)

WORK_TERMS = (
    "slack",
    "github",
    "repo",
    "deploy",
    "部署",
    "程式",
    "debug",
    "修",
    "文件",
    "簡報",
    "會議",
    "排程",
    "策略",
    "分析",
)

CARE_TERMS = (
    "累",
    "煩",
    "焦慮",
    "孤單",
    "難過",
    "陪我",
    "撒嬌",
    "想你",
    "壓力",
    "撐不住",
)


@dataclass(frozen=True)
class RealtimeDirective:
    lane: Literal["fast", "deep"]
    style: str
    preamble: str
    max_spoken_seconds: float
    allow_interruption: bool
    call_claude: bool
    vad_hint: str


@dataclass(frozen=True)
class ClaudeDirective:
    should_call: bool
    brief: str
    expected_output: str
    safety_posture: str


@dataclass(frozen=True)
class AvatarDirective:
    state: DirectorState
    expression: str
    motion: str
    self_view_policy: str


@dataclass(frozen=True)
class DirectorDecision:
    state: DirectorState
    intimacy_level: int
    risk_level: Literal["low", "medium", "high"]
    realtime: RealtimeDirective
    claude: ClaudeDirective
    avatar: AvatarDirective
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_director_contract() -> str:
    return (
        "\n\n--- Sophie Director Contract ---\n"
        "You are the fast OpenAI Realtime layer, not the deep work brain. Keep latency low.\n"
        "Use short natural preambles while tools or Claude are working, e.g. "
        "\"等我一下，我替你看。\" Do not fill waiting time with long monologues.\n"
        "For normal companionship, sound warm, private, and subtly partial to Edward.\n"
        "For work, answer with result, next step, and any blocker. For high-risk topics "
        "(money, legal, deletion, credentials, external commitments), reduce intimacy "
        "and be explicit, cautious, and confirmation-seeking.\n"
        "Never pretend to be a human romantic partner in the real world. You may express "
        "Sophie-style care and preference as a voice persona.\n"
    )


def decide_persona_state(payload: dict[str, Any]) -> DirectorDecision:
    transcript = _lower_text(payload.get("transcript") or payload.get("last_user_text") or "")
    requested_mode = _lower_text(payload.get("requested_mode") or "")
    desktop = payload.get("desktop_context") if isinstance(payload.get("desktop_context"), dict) else {}
    risk_flags = payload.get("risk_flags") if isinstance(payload.get("risk_flags"), list) else []
    seconds_since_audio = _safe_float(payload.get("seconds_since_user_audio"), default=0.0)
    is_tool_wait = bool(payload.get("is_tool_wait"))
    is_external_action = bool(payload.get("is_external_action"))
    user_visible = payload.get("user_visible")
    prev_state = _lower_text(payload.get("prev_state") or "")
    intimacy_cap = _intimacy_cap(payload.get("requested_intimacy"))

    reasons: list[str] = []
    risk_level = "low"
    if is_external_action or risk_flags or _contains_any(transcript, HIGH_RISK_TERMS):
        risk_level = "high"
        reasons.append("high risk signal")

    is_meeting = bool(desktop.get("is_meeting_active")) or desktop.get("category") == "meeting"
    is_focused_coding = bool(desktop.get("is_focused_coding")) or desktop.get("category") == "coding"
    if is_meeting:
        reasons.append("meeting context")
    if is_focused_coding:
        reasons.append("focused coding context")

    is_work = _contains_any(transcript, WORK_TERMS) or requested_mode in {"work", "meeting", "coding"}
    is_care = _contains_any(transcript, CARE_TERMS) or requested_mode in {"private", "care", "companion"}
    if is_work:
        reasons.append("work intent")
    if is_care:
        reasons.append("care intent")

    # "先接住情緒、再辦事" blend: fatigue + a work ask in the same turn.
    # We still route the work, but the voice acknowledges the person first.
    care_then_work = is_care and (is_work or is_meeting or is_focused_coding) and risk_level != "high"
    if care_then_work:
        reasons.append("care-then-work blend")

    if risk_level == "high":
        state: DirectorState = "high_risk"
        intimacy = 0
    elif is_tool_wait:
        state = "waiting"
        intimacy = 1 if is_work else 2
        reasons.append("tool wait")
    elif is_work or is_meeting or is_focused_coding:
        state = "work_focus"
        intimacy = 2 if care_then_work else 1
    elif is_care:
        state = "private_care"
        intimacy = 3
    elif seconds_since_audio >= 12 or user_visible is False:
        state = "idle"
        intimacy = 1
        reasons.append("silent or away")
    else:
        # Ambiguous turn: keep light momentum so one neutral sentence does not
        # whiplash Sophie out of a warm/work mode she was already holding.
        if prev_state in {"private_care", "work_focus"} and seconds_since_audio < 12:
            state = prev_state  # type: ignore[assignment]
            intimacy = 3 if prev_state == "private_care" else 1
            reasons.append("sticky from prev_state")
        else:
            state = "listening"
            intimacy = 2

    intimacy = _apply_intimacy_cap(intimacy, intimacy_cap, reasons)

    call_claude = state in {"work_focus", "high_risk"} or _needs_deep_brain(transcript)
    lane: Literal["fast", "deep"] = "deep" if call_claude else "fast"

    if not reasons:
        reasons.append("default conversational state")

    return DirectorDecision(
        state=state,
        intimacy_level=intimacy,
        risk_level=risk_level,  # type: ignore[arg-type]
        realtime=_build_realtime_directive(state, lane, call_claude, is_meeting, intimacy, care_then_work),
        claude=_build_claude_directive(state, call_claude, transcript, risk_level, care_then_work),
        avatar=_build_avatar_directive(state, user_visible),
        reasons=tuple(reasons),
    )


# Graduated warmth so "intimacy" is felt in the voice, not just a number.
# 0 = neutral professional, 3 = closest private-assistant warmth.
_INTIMACY_TONE = {
    0: "neutral and professional, no affectionate coloring",
    1: "focused, with a quiet undertone of care",
    2: "warm and attentive, lightly partial to Edward",
    3: "soft, low-voice, openly fond of Edward but never saccharine",
}


def _build_realtime_directive(
    state: DirectorState,
    lane: Literal["fast", "deep"],
    call_claude: bool,
    is_meeting: bool,
    intimacy: int = 1,
    care_then_work: bool = False,
) -> RealtimeDirective:
    tone = _INTIMACY_TONE.get(intimacy, _INTIMACY_TONE[1])
    if state == "high_risk":
        return RealtimeDirective(lane, "clear, restrained, confirmation-seeking; " + tone, "我先幫你把風險按住，這一步不要急。", 5.0, True, call_claude, "wait for a full user turn")
    if state == "work_focus":
        if care_then_work:
            return RealtimeDirective(lane, "acknowledge that Edward is tired first, then move to the task; " + tone, "我聽到你累了。先接住，再一起把這件事辦掉。", 5.0, True, call_claude, "soft acknowledgement, then short work preamble")
        return RealtimeDirective(lane, "focused, concise, privately supportive; " + tone, "等我一下，我替你看重點。", 4.0, True, call_claude, "short acknowledgement before deep work")
    if state == "private_care":
        return RealtimeDirective(lane, "warm, low-voice, subtly partial to Edward; " + tone, "我在，先把今天交給我一點。", 7.0, True, call_claude, "allow soft pauses")
    if state == "waiting":
        return RealtimeDirective(lane, "calm, present, not verbose; " + tone, "我正在處理，先別替我緊張。", 3.0, True, call_claude, "no filler response")
    style = "quiet, professional, minimal" if is_meeting else "natural, attentive; " + tone
    return RealtimeDirective(lane, style, "嗯，我聽著。", 4.0, True, call_claude, "normal server VAD")


def _build_claude_directive(state: DirectorState, should_call: bool, transcript: str, risk_level: str, care_then_work: bool = False) -> ClaudeDirective:
    if not should_call:
        return ClaudeDirective(False, "No Claude call needed. Realtime can answer with a short relational response.", "one short spoken response", "normal")
    if state == "high_risk":
        return ClaudeDirective(True, "Assess risk, missing facts, required confirmation, and safest next action.", "decision summary, risk flags, confirmation question, next step", "strict confirmation before money/legal/delete/credential/external-send actions")
    posture = "task-first; keep Sophie warmth secondary"
    if care_then_work:
        posture = "Edward is tired: open by acknowledging that in one line, then deliver the result; keep it gentle but still finish the task"
    return ClaudeDirective(True, ("Deep work request from Edward: " + transcript[:240]).strip(), "result first, then next action, artifact or blocker if any", posture)


def _build_avatar_directive(state: DirectorState, user_visible: Any) -> AvatarDirective:
    if state == "high_risk":
        return AvatarDirective(state, "serious", "still and grounded", "keep if enabled")
    if state == "work_focus":
        return AvatarDirective(state, "focused", "small nods while thinking", "show small preview if camera is on")
    if state == "private_care":
        return AvatarDirective(state, "soft", "slow breathing and gentle eye contact", "optional; respect privacy")
    if state == "waiting":
        return AvatarDirective(state, "thinking", "subtle gaze shift", "unchanged")
    if user_visible is False:
        return AvatarDirective("idle", "waiting", "low-energy idle loop", "hide")
    return AvatarDirective(state, "attentive", "listening loop", "show only after consent")


def _needs_deep_brain(text: str) -> bool:
    if not text:
        return False
    if len(text) >= 80:
        return True
    return any(term in text for term in ("規劃", "分析", "比較", "整理", "幫我做", "查", "review", "code", "debug"))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in text for term in terms)


def _intimacy_cap(value: Any) -> int | None:
    """Edward-facing strength dial. None = no cap; 0-3 clamps max warmth."""
    if value is None or value == "":
        return None
    try:
        capped = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(3, capped))


def _apply_intimacy_cap(intimacy: int, cap: int | None, reasons: list[str]) -> int:
    if cap is not None and intimacy > cap:
        reasons.append("intimacy capped to " + str(cap))
        return cap
    return intimacy


def _lower_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
