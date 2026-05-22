# castle-voice-engine / castle/safety/
# (c) 2026 Edward / BeyondPath
#
# 安全守則程式碼層 implementation · ADR-018 / ADR-020 hard rules 落 code
#
# 跨 Phase 共用 (Phase 2 後半段 SpeechBrain enrollment / Phase 3 鏡頭 / Phase 3.2 SoulX)

from castle.safety.subject_guard import (
    SubjectGuardError,
    SallyHardRule,
    enforce_subject_whitelist,
    check_age_metadata,
)

__all__ = [
    "SubjectGuardError",
    "SallyHardRule",
    "enforce_subject_whitelist",
    "check_age_metadata",
]
