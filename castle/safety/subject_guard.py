# castle-voice-engine / castle/safety/subject_guard.py
# (c) 2026 Edward / BeyondPath
#
# Sally 6 歲 hard rule + 未成年保護 · ADR-018 + ADR-020 落 code
#
# 跨 Phase 共用守則:
#   - Phase 2 後半段 SpeechBrain enrollment (voice sample)
#   - Phase 3 鏡頭多模態 (camera frame + face embedding)
#   - Phase 3.2 SoulX-FlashHead (cond_image + audio · digital face clone)
#
# 觸發點:
#   - 任何 enrollment / inference / sample upload endpoint 必過此 guard
#   - 命中 hard rule 立刻 raise SubjectGuardError · 拒絕處理
#
# 隱私守則:
#   - 不存 subject 識別資訊 (只標 OK / NOT OK · 不寫 audit log 含名字)
#   - hard rule violation 寫 stderr (不寫磁碟、不上雲)
#
# 設計原則:
#   - 預設 deny · whitelist explicit 才允許
#   - hard rule 不可關閉 (CAMERA_DISABLE 那種 env var 不適用)
#   - 跨 endpoint 一致 enforcement

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class SubjectGuardError(Exception):
    """Hard rule violation · 不可繞過、不可 catch and ignore."""
    pass


@dataclass(frozen=True)
class SallyHardRule:
    """
    Sally 6 歲 hard rule · ADR-018 + ADR-020 + sulima Phase 3.1 第 36-55 條.

    對應 lesson_2026-05-22 + project_voice_path ADR-021:
      - Edward 自己樣本: OK
      - Qiana informed consent: OK
      - Sally 6 歲: NEVER (即使自用 · 即使 Edward 父權主張)
      - 訪客 / 陌生人: NEVER

    這是憲法級 hard rule · 不可關閉 · 跨 ADR-020 雙軌（Track A 個人自用也守）。
    """

    REASON: str = (
        "Sally 6 歲未成年生物特徵永不餵未經 audit 的 model · "
        "ADR-018 + ADR-020 + Phase 3.1 第 36-55 條 (sulima verdict 2026-05-22) · "
        "個人自用 / 商業化 / 任何用途皆禁"
    )


# Whitelist 允許名單 (explicit · 預設都不允許)
_ALLOWED_SUBJECTS = frozenset({
    "edward",          # Edward 自己 (用戶 + owner)
    "qiana",           # Qiana 自願 informed consent (成年 · 須親自簽 consent)
    "self",            # 用戶自己 (匿名 alias for Edward)
    "speaker_unknown", # 未明確標的成年人 sample (預設信任 · 由 Edward 把關上傳)
})

_DENIED_SUBJECTS = frozenset({
    "sally",          # 6 歲女兒 hard rule
    "minor",          # 任何未成年通用 alias
    "child",          # 任何兒童通用 alias
    "stranger",       # 陌生人 (Phase 3 鏡頭 visitor) · 不主動 enroll
    "visitor",        # 訪客 (camera_endpoints.py 已 cover)
})

# 未成年年齡硬條件 (跟公司國籍 / 用途無關 · 跨 ADR-020 雙軌守)
_MINOR_AGE_THRESHOLD = 18  # 18 歲以下視為未成年 · GDPR Article 8 + 台灣個資法 + COPPA 同盟最嚴


def enforce_subject_whitelist(
    subject: str,
    operation: str = "unknown_op",
) -> None:
    """
    Hard rule enforcement · 命中 deny list 直接 raise.

    Args:
        subject: subject identifier (lowercase · 不含敏感資訊 · 只是 alias)
        operation: 觸發此 check 的 operation name (for stderr log only · 不寫磁碟)

    Raises:
        SubjectGuardError: 命中 deny list / 不在 whitelist · 不可繞過

    Examples:
        >>> enforce_subject_whitelist("edward", "voice_enrollment")  # OK
        >>> enforce_subject_whitelist("sally", "voice_enrollment")  # raises
        >>> enforce_subject_whitelist("unknown_kid", "voice_enrollment")  # raises (預設 deny)
    """
    subj_lower = (subject or "").strip().lower()

    if not subj_lower:
        raise SubjectGuardError(
            f"[{operation}] subject 標籤為空 · 預設拒絕 (must whitelist explicit)"
        )

    if subj_lower in _DENIED_SUBJECTS:
        logger.warning(
            "[safety.subject_guard] HARD RULE TRIGGERED · operation=%s subject=%s reason=%s",
            operation,
            subj_lower,
            SallyHardRule.REASON,
        )
        raise SubjectGuardError(
            f"[{operation}] subject={subj_lower!r} · hard rule deny · {SallyHardRule.REASON}"
        )

    if subj_lower not in _ALLOWED_SUBJECTS:
        # 預設 deny · whitelist 沒明寫的視為不允許
        logger.warning(
            "[safety.subject_guard] UNKNOWN subject blocked · operation=%s subject=%s · "
            "must be in whitelist: %s",
            operation,
            subj_lower,
            sorted(_ALLOWED_SUBJECTS),
        )
        raise SubjectGuardError(
            f"[{operation}] subject={subj_lower!r} · not in whitelist · "
            f"add explicit allowlist entry first (with Edward 親口 review)"
        )

    logger.info(
        "[safety.subject_guard] OK · operation=%s subject=%s",
        operation,
        subj_lower,
    )


def check_age_metadata(
    age: Optional[int],
    subject: str = "unknown",
    operation: str = "unknown_op",
) -> None:
    """
    Age metadata check · 補 enforce_subject_whitelist 的另一層 (有些上傳含 age metadata).

    若 age < 18 · 視為未成年 · 不論 subject label · raise.

    Args:
        age: 年齡 metadata · None 視為 unknown (預設信任 · 由 subject whitelist 把關)
        subject: subject label (for log)
        operation: 觸發此 check 的 operation name

    Raises:
        SubjectGuardError: age < 18 · 不可繞過
    """
    if age is None:
        return  # unknown age · 信 subject whitelist

    if age < _MINOR_AGE_THRESHOLD:
        logger.warning(
            "[safety.subject_guard] AGE HARD RULE · operation=%s subject=%s age=%s · "
            "未成年 (< %s) 永不餵未經 audit 的 model",
            operation,
            subject,
            age,
            _MINOR_AGE_THRESHOLD,
        )
        raise SubjectGuardError(
            f"[{operation}] subject={subject!r} age={age} · "
            f"under {_MINOR_AGE_THRESHOLD} · {SallyHardRule.REASON}"
        )


# === Integration points (for Phase 3.2 SoulX integration) ===
#
# castle/server/soulx_endpoints.py:
#   @app.post("/soulx/stream")
#   async def soulx_stream_endpoint(req: SoulxStreamRequest):
#       enforce_subject_whitelist(req.subject, "soulx_inference")
#       check_age_metadata(req.age, req.subject, "soulx_inference")
#       ...
#
# castle/integrations/speechbrain_voiceid.py:
#   def enroll_speaker(audio_path: str, subject: str = "edward"):
#       enforce_subject_whitelist(subject, "voiceid_enroll")
#       ...
#
# castle/multimodal/face_identity.py (Phase 3.1.2+):
#   def enroll_face(image_path: str, subject: str, age: int):
#       enforce_subject_whitelist(subject, "face_enroll")
#       check_age_metadata(age, subject, "face_enroll")
#       ...
#
# === Test the rule (smoke) ===
#
# python -c "from castle.safety import enforce_subject_whitelist; \
#            enforce_subject_whitelist('edward', 'test')"  # OK
# python -c "from castle.safety import enforce_subject_whitelist; \
#            enforce_subject_whitelist('sally', 'test')"  # raises
