# castle-voice-engine - v0.3.0 Phase 2 (Path B)
# castle/server/text_correction.py
#
# Lightweight Chinese STT post-correction layer:
#   1) Dictionary-based homophone / common-STT-error replacements (fast, cheap).
#   2) spaCy zh NER pass for entity boundary detection (optional; degrades
#      gracefully if model not installed -> dict-only mode).
#
# Why this matters: OpenAI gpt-4o-transcribe zh is good but still flubs domain
# words specific to Edward's world: castle / agent names ("蕪菁頭" -> "無菁頭",
# "卡西法" -> "卡斯法", "BeyondPath" -> "biyond path", etc.). One short pass here
# gives a much better transcript before it ends up displayed in the UI or fed
# back to Claude as quoting context.
#
# This module is sync + cheap: no model calls, no network. spaCy load is lazy.

from __future__ import annotations

import re
from typing import Optional

# --- 常見 STT 錯字 / 同音字 dict ----------------------------------------------
# key = STT 常吐錯的形式, value = 正確形式. Order matters (longer keys first).
_HOMOPHONE_DICT: dict[str, str] = {
    # 城堡 7 人 subagent
    "無菁頭": "蕪菁頭",
    "無精頭": "蕪菁頭",
    "蘿菁頭": "蕪菁頭",
    "卡斯法": "卡西法",
    "卡西發": "卡西法",
    "卡式法": "卡西法",
    "霍而": "霍爾",
    "Howl": "霍爾",
    "馬路克": "馬魯克",
    "馬陸克": "馬魯克",
    "Markl": "馬魯克",
    "馬克": "馬魯克",
    "蘇曼納": "沙利曼",  # sophie.yaml 也搞錯過、order matters
    "蘇里曼": "沙利曼",
    "沙力曼": "沙利曼",
    "Suliman": "沙利曼",
    "Sulima": "沙利曼",
    "蘇菲": "蘇菲",  # canonical (no-op, but pin it)
    "Sophie": "蘇菲",
    "Hawl": "霍爾",
    # 產品 / 品牌
    "biyond path": "BeyondPath",
    "beyondpath": "BeyondPath",
    "Beyond path": "BeyondPath",
    "比揚path": "BeyondPath",
    "Beyond Spec": "BeyondSpec",
    "voice path": "Voice Path",
    "Voicepath": "Voice Path",
    "Hire Path": "HirePath",
    "hairpath": "HirePath",
    # 技術
    "Modal": "Modal",
    "morder": "Modal",
    "Module": "Modal",  # 經常被誤聽
    "API key": "API key",
    "Anthropic": "Anthropic",
    "AnthropicAI": "Anthropic",
    "Anthropic AI": "Anthropic",
    "Clord": "Claude",
    "kloard": "Claude",
    "OpenAI": "OpenAI",
    "openAI": "OpenAI",
    # 系統 / SOP 詞
    "嘿斯特":  "Howl",
    "EJ":  "Edge",
}

# Sort by key length DESC so longer phrases replace first (avoid partial collisions).
_SORTED_KEYS = sorted(_HOMOPHONE_DICT.keys(), key=len, reverse=True)
_REPLACE_PATTERN = re.compile("|".join(re.escape(k) for k in _SORTED_KEYS)) if _SORTED_KEYS else None


_SPACY_NLP = None
_SPACY_TRIED = False


def _try_load_spacy():
    """Lazy-load spaCy zh model. Returns None if unavailable (no crash)."""
    global _SPACY_NLP, _SPACY_TRIED
    if _SPACY_TRIED:
        return _SPACY_NLP
    _SPACY_TRIED = True
    try:
        import spacy  # noqa: PLC0415
        _SPACY_NLP = spacy.load("zh_core_web_sm")
    except Exception:  # noqa: BLE001
        _SPACY_NLP = None
    return _SPACY_NLP


def _apply_dict_corrections(text: str) -> tuple[str, list[dict]]:
    """Apply homophone dict. Returns (corrected_text, list_of_changes)."""
    if not text or _REPLACE_PATTERN is None:
        return text, []
    changes = []

    def _sub(match: re.Match) -> str:
        original = match.group(0)
        corrected = _HOMOPHONE_DICT.get(original, original)
        if corrected != original:
            changes.append({
                "type": "homophone",
                "from": original,
                "to": corrected,
                "pos": match.start(),
            })
        return corrected

    new_text = _REPLACE_PATTERN.sub(_sub, text)
    return new_text, changes


def _extract_entities_spacy(text: str) -> list[dict]:
    """Use spaCy zh NER to extract named entities (PERSON / ORG / GPE etc)."""
    nlp = _try_load_spacy()
    if nlp is None or not text:
        return []
    try:
        doc = nlp(text)
        return [{"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char} for ent in doc.ents]
    except Exception:  # noqa: BLE001
        return []


def correct_text(text: str, use_spacy: bool = True) -> dict:
    """Main entry point. Returns:
        {
          original: str,
          corrected: str,
          changes: [ {type, from, to, pos}, ... ],
          entities: [ {text, label, start, end}, ... ],  # spaCy results, may be []
          spacy_available: bool,
        }
    """
    if not text:
        return {"original": "", "corrected": "", "changes": [], "entities": [], "spacy_available": _try_load_spacy() is not None}

    corrected, changes = _apply_dict_corrections(text)
    entities = _extract_entities_spacy(corrected) if use_spacy else []
    return {
        "original": text,
        "corrected": corrected,
        "changes": changes,
        "entities": entities,
        "spacy_available": _try_load_spacy() is not None,
    }


def get_dict_size() -> int:
    return len(_HOMOPHONE_DICT)
