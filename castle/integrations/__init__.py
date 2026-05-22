# castle-voice-engine - castle/integrations/
# (c) 2026 Edward / BeyondPath
#
# Voice Path v2.0 Phase 2 後半段：本機跑的 voice 配件整合
#
# 含:
#   - picovoice.py  → Porcupine 中文喚醒詞 + Eagle 聲紋認證 (本機跑、Apache-2.0)
#   - spacy_ner.py  → 中文 NER 個資過濾 (本機跑、MIT)
#
# 設計原則：
#   - 整合骨架先寫、Edward 動完物理動作 (申請 AccessKey / 下載 .ppn / 安裝模型) 就接上
#   - 預設 OFF、env var 開
#   - 隱私: 全部本機跑、不上雲 (ADR-018 100% 不出 Edward 機器一條)

from castle.integrations.picovoice import (
    PicovoiceConfig,
    is_picovoice_ready,
    init_porcupine,
    init_eagle_recognizer,
)
from castle.integrations.spacy_ner import (
    SpacyNerConfig,
    is_spacy_ready,
    redact_pii,
)
from castle.integrations.speechbrain_voiceid import (
    SpeechBrainConfig,
    is_speechbrain_ready,
    enroll_speaker,
    verify_speaker,
)

__all__ = [
    # Tavus CVI exports
    "TavusAPIError",
    "tavus_create_persona",
    "tavus_get_persona",
    "tavus_create_replica_from_image",
    "tavus_get_replica",
    "tavus_create_conversation",
    "tavus_get_conversation",
    "tavus_end_conversation",
    "TAVUS_DEFAULT_STOCK_REPLICA",
    "TAVUS_STOCK_REPLICA_ANNA",
    # SpeechBrain (主路 · Picovoice Eagle 開源替代 · 2026-05-22 ship)
    "SpeechBrainConfig",
    "is_speechbrain_ready",
    "enroll_speaker",
    "verify_speaker",
    # spaCy NER (個資遮罩)
    "SpacyNerConfig",
    "is_spacy_ready",
    "redact_pii",
    # Picovoice (deprecated · 改企業版 only · 保留 archive)
    "PicovoiceConfig",
    "is_picovoice_ready",
    "init_porcupine",
    "init_eagle_recognizer",
]

# Tavus CVI (Phase 3.2 · 2026-05-23 卡西法 ship · ADR-020 Track A 走 SaaS · Anam audit pending)
from castle.integrations.tavus_client import (
    TavusAPIError,
    create_persona as tavus_create_persona,
    get_persona as tavus_get_persona,
    create_replica_from_image as tavus_create_replica_from_image,
    get_replica as tavus_get_replica,
    create_conversation as tavus_create_conversation,
    get_conversation as tavus_get_conversation,
    end_conversation as tavus_end_conversation,
    DEFAULT_STOCK_REPLICA as TAVUS_DEFAULT_STOCK_REPLICA,
    STOCK_REPLICA_ANNA as TAVUS_STOCK_REPLICA_ANNA,
)
