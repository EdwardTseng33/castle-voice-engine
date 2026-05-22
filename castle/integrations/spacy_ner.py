# castle-voice-engine - castle/integrations/spacy_ner.py
# (c) 2026 Edward / BeyondPath
#
# 中文 NER 個資過濾 (本機跑、敏感字遮罩)
# Voice Path v2.0 Phase 2 後半段
#
# 用法 (PoC 階段):
#   - browser 在 partial_transcript / final_transcript event 收到 user 講的文字後
#     若該 transcript 要寫到任何 log / 通知 / dispatch brief 之前
#     先跑 redact_pii() 過一層
#   - 不影響 voice 即時 loop (Sophie 跟 Edward 對話的內容 OpenAI 已收、
#     本層是擋「向第 3 方流出」前的最後一道)
#
# 隱私守則 (對應 security-architecture-checklist.md + ADR-018):
#   - 1.5 PII detection: 姓名 / email / 手機 / 身分證 / 信用卡
#   - 5.4 不主動收集敏感資料: 偵測到就 [REDACTED] 替換
#   - 6.4 第三方信任: spaCy (Explosion AI · MIT · 本機跑)
#   - 6.7 license: MIT (商用 OK)
#
# 模型選擇：
#   - zh_core_web_sm (小、~50MB、夠 PoC) - default
#   - zh_core_web_md (中、~150MB、精準度更好)
#   - zh_core_web_trf (大、~500MB、最準但慢)
#
# Edward 要做的物理動作 (一次):
#   python -m spacy download zh_core_web_sm
#   (一行、< 2 分鐘 · 寫進 EDWARD-PICOVOICE-2-STEPS.md 一起講)

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_spacy_nlp = None  # cache loaded model


def _lazy_load_spacy(model_name: str = "zh_core_web_sm"):
    global _spacy_nlp
    if _spacy_nlp is not None:
        return _spacy_nlp
    try:
        import spacy  # type: ignore
    except ImportError:
        return None
    try:
        _spacy_nlp = spacy.load(model_name)
        return _spacy_nlp
    except OSError:
        logger.info(
            "spaCy 中文模型 %s 沒下載、NER OFF (跑: python -m spacy download %s)",
            model_name,
            model_name,
        )
        return None


# 高信心 regex pattern (spaCy 抓不到的補位)
_PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "PHONE_TW": re.compile(r"\b09\d{8}\b|\b09\d{2}-?\d{3}-?\d{3}\b"),  # 台灣手機 09xxxxxxxx
    "PHONE_GENERIC": re.compile(r"\b\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"),
    "TW_ID": re.compile(r"\b[A-Z][12]\d{8}\b"),  # 台灣身分證
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # 4 段 13-16 位
}


@dataclass
class SpacyNerConfig:
    model_name: str = "zh_core_web_sm"
    redact_persons: bool = True       # spaCy PERSON entities
    redact_emails: bool = True
    redact_phones: bool = True
    redact_ids: bool = True
    redact_credit_cards: bool = True
    redact_gpe: bool = False          # 國家 / 城市 (預設不擋、太常用 · Edward 講「台北」不該被遮)
    redaction_token: str = "[REDACTED]"

    @classmethod
    def from_env(cls) -> "SpacyNerConfig":
        return cls(
            model_name=os.environ.get("SPACY_ZH_MODEL", "zh_core_web_sm").strip(),
            redact_persons=os.environ.get("REDACT_PERSONS", "1") != "0",
            redact_emails=os.environ.get("REDACT_EMAILS", "1") != "0",
            redact_phones=os.environ.get("REDACT_PHONES", "1") != "0",
            redact_ids=os.environ.get("REDACT_IDS", "1") != "0",
            redact_credit_cards=os.environ.get("REDACT_CREDIT_CARDS", "1") != "0",
            redact_gpe=os.environ.get("REDACT_GPE", "0") != "0",
        )


def is_spacy_ready(cfg: Optional[SpacyNerConfig] = None) -> dict[str, bool]:
    """檢查 spaCy + 模型有沒有 ready。"""
    if cfg is None:
        cfg = SpacyNerConfig.from_env()
    try:
        import spacy  # type: ignore
        spacy_installed = True
    except ImportError:
        spacy_installed = False
    model_loaded = _lazy_load_spacy(cfg.model_name) is not None
    return {
        "spacy_installed": spacy_installed,
        "model_loaded": model_loaded,
    }


def _redact_with_regex(text: str, cfg: SpacyNerConfig) -> tuple[str, list[dict]]:
    """先跑 regex pass (高信心、低成本)、回 (redacted_text, hits)."""
    hits = []
    out = text
    pattern_map = []
    if cfg.redact_emails:
        pattern_map.append(("EMAIL", _PATTERNS["EMAIL"]))
    if cfg.redact_phones:
        pattern_map.append(("PHONE_TW", _PATTERNS["PHONE_TW"]))
        pattern_map.append(("PHONE_GENERIC", _PATTERNS["PHONE_GENERIC"]))
    if cfg.redact_ids:
        pattern_map.append(("TW_ID", _PATTERNS["TW_ID"]))
    if cfg.redact_credit_cards:
        pattern_map.append(("CREDIT_CARD", _PATTERNS["CREDIT_CARD"]))

    for label, pat in pattern_map:
        matches = list(pat.finditer(out))
        for m in matches:
            hits.append({
                "label": label,
                "match": m.group(0),
                "start": m.start(),
                "end": m.end(),
                "source": "regex",
            })
        out = pat.sub(cfg.redaction_token, out)
    return out, hits


def _redact_with_spacy(text: str, cfg: SpacyNerConfig) -> tuple[str, list[dict]]:
    """spaCy NER pass (抓 PERSON / GPE 等)、回 (redacted_text, hits)."""
    nlp = _lazy_load_spacy(cfg.model_name)
    if nlp is None:
        return text, []

    doc = nlp(text)
    hits = []
    spans_to_redact = []
    for ent in doc.ents:
        should_redact = False
        if cfg.redact_persons and ent.label_ == "PERSON":
            should_redact = True
        elif cfg.redact_gpe and ent.label_ == "GPE":
            should_redact = True
        if should_redact:
            spans_to_redact.append((ent.start_char, ent.end_char, ent.label_, ent.text))

    # 倒序 replace 避免位移錯
    spans_to_redact.sort(key=lambda s: s[0], reverse=True)
    out = text
    for start, end, label, original in spans_to_redact:
        hits.append({
            "label": label,
            "match": original,
            "start": start,
            "end": end,
            "source": "spacy",
        })
        out = out[:start] + cfg.redaction_token + out[end:]
    # hits 順序回正
    hits.sort(key=lambda h: h["start"])
    return out, hits


def redact_pii(
    text: str,
    cfg: Optional[SpacyNerConfig] = None,
) -> tuple[str, list[dict]]:
    """
    過濾 PII、回 (redacted_text, hits_list).

    Args:
        text: 原始文字 (例: user transcript)
        cfg: SpacyNerConfig (None = from env)

    Returns:
        redacted_text: 替換 [REDACTED] 後的文字
        hits: 列表、每個 hit 含 label / match / start / end / source

    Pipeline:
        1. regex pass (email / phone / id / credit card · 高信心 fast path)
        2. spaCy NER pass (PERSON / GPE 視 config)

    沒安裝 spacy 或模型沒下載 → regex pass 仍跑、spaCy pass 跳過 (degraded mode)
    """
    if cfg is None:
        cfg = SpacyNerConfig.from_env()
    if not text or not text.strip():
        return text, []

    # Stage 1 · regex (fast, high confidence)
    out, regex_hits = _redact_with_regex(text, cfg)
    # Stage 2 · spaCy (slower, broader)
    out, spacy_hits = _redact_with_spacy(out, cfg)

    return out, regex_hits + spacy_hits
