# castle-voice-engine - castle/integrations/picovoice.py
# (c) 2026 Edward / BeyondPath
#
# Picovoice Porcupine (中文喚醒詞「蘇菲」) + Eagle (聲紋認 Edward) 整合骨架
# Voice Path v2.0 Phase 2 後半段
#
# 為什麼是骨架：
#   - Edward 必須親自動 2 件物理動作 (見 EDWARD-PICOVOICE-2-STEPS.md):
#     1. https://console.picovoice.ai 申請 AccessKey (Google login · 免費)
#     2. Console 訓練「蘇菲」中文喚醒詞、下載 .ppn 檔
#   - 鑰匙 + .ppn 都到位 → 此檔即可載入跑、不必再改程式
#
# 隱私守則 (對應 security-architecture-checklist.md + ADR-018):
#   - 1.1-1.6 資料流：聲紋特徵跟喚醒判定 100% 本機推論、不上雲
#   - 2.4 token: PICOVOICE_ACCESS_KEY 從 .env 讀、不 hardcode
#   - 6.4 第三方信任: Picovoice (加拿大公司 · SOC 2 Type II · 本機 SDK)
#   - 6.7 license: Picovoice 個人版免費 / 商用 $499/月+ (PoC 階段 OK)

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Picovoice SDK lazy import (避免沒裝就炸)
_pvporcupine = None
_pveagle = None


def _lazy_import_porcupine():
    global _pvporcupine
    if _pvporcupine is not None:
        return _pvporcupine
    try:
        import pvporcupine  # type: ignore
        _pvporcupine = pvporcupine
        return pvporcupine
    except ImportError:
        return None


def _lazy_import_eagle():
    global _pveagle
    if _pveagle is not None:
        return _pveagle
    try:
        import pveagle  # type: ignore
        _pveagle = pveagle
        return pveagle
    except ImportError:
        return None


@dataclass
class PicovoiceConfig:
    access_key: str = ""
    wake_word_ppn_path: str = ""           # 「蘇菲」.ppn 檔 (Edward 從 console 下載)
    chinese_model_pv_path: str = ""        # porcupine_params_zh.pv (中文模型 · SDK 內附)
    eagle_profile_path: str = ""           # 註冊好的 Edward .bin (跑 register_eagle_speaker.py 產出)
    verification_threshold: float = 0.5    # Eagle score 門檻 (> 0.5 = match)

    @classmethod
    def from_env(cls) -> "PicovoiceConfig":
        """從 env var / .env 讀設定 (避免 hardcode)."""
        return cls(
            access_key=os.environ.get("PICOVOICE_ACCESS_KEY", "").strip(),
            wake_word_ppn_path=os.environ.get(
                "PICOVOICE_WAKE_WORD_PPN",
                "breeze_poc/phase2-poc/wake_words/sophie_zh.ppn",
            ).strip(),
            chinese_model_pv_path=os.environ.get(
                "PICOVOICE_ZH_MODEL_PV",
                "breeze_poc/phase2-poc/wake_words/porcupine_params_zh.pv",
            ).strip(),
            eagle_profile_path=os.environ.get(
                "PICOVOICE_EAGLE_PROFILE",
                "breeze_poc/phase2-poc/edward_eagle_profile.bin",
            ).strip(),
            verification_threshold=float(
                os.environ.get("PICOVOICE_EAGLE_THRESHOLD", "0.5")
            ),
        )


def is_picovoice_ready(cfg: Optional[PicovoiceConfig] = None) -> dict[str, bool]:
    """
    回 Edward 4 個物理動作各自做完沒、給 STATUS endpoint 用。

    Returns:
        {
            "access_key_set": bool,        # Edward 申請了 AccessKey 沒
            "wake_word_ppn_exists": bool,  # Edward 訓練了「蘇菲」.ppn 沒
            "zh_model_exists": bool,       # 中文 .pv 模型 (SDK 內附、應該 True)
            "eagle_profile_exists": bool,  # Edward 跑過 register 沒
            "porcupine_sdk_installed": bool,
            "eagle_sdk_installed": bool,
        }
    """
    if cfg is None:
        cfg = PicovoiceConfig.from_env()

    base_dir = Path(__file__).resolve().parent.parent.parent  # castle-voice-engine root

    def _abs(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else base_dir / path

    return {
        "access_key_set": bool(cfg.access_key),
        "wake_word_ppn_exists": _abs(cfg.wake_word_ppn_path).exists(),
        "zh_model_exists": _abs(cfg.chinese_model_pv_path).exists(),
        "eagle_profile_exists": _abs(cfg.eagle_profile_path).exists(),
        "porcupine_sdk_installed": _lazy_import_porcupine() is not None,
        "eagle_sdk_installed": _lazy_import_eagle() is not None,
    }


def init_porcupine(cfg: Optional[PicovoiceConfig] = None):
    """
    建立 Porcupine wake word detector。

    Edward 必須先做完 EDWARD-PICOVOICE-2-STEPS.md 兩件事:
      1. 申請 AccessKey、貼到 .env (PICOVOICE_ACCESS_KEY=...)
      2. Console 訓練「蘇菲」、把 .ppn 放到 wake_words/

    Returns:
        porcupine instance 或 None (沒 ready 時)
    """
    pvporcupine = _lazy_import_porcupine()
    if pvporcupine is None:
        logger.info("pvporcupine 未安裝、跳過 wake word")
        return None

    if cfg is None:
        cfg = PicovoiceConfig.from_env()

    ready = is_picovoice_ready(cfg)
    if not ready["access_key_set"]:
        logger.info("PICOVOICE_ACCESS_KEY 沒設、wake word OFF (Edward 起床去 console.picovoice.ai 申請)")
        return None
    if not ready["wake_word_ppn_exists"]:
        logger.info(
            "「蘇菲」.ppn 不存在 (path: %s)、wake word OFF (Edward 起床去 console 訓練)",
            cfg.wake_word_ppn_path,
        )
        return None

    base_dir = Path(__file__).resolve().parent.parent.parent

    def _abs(p: str) -> str:
        path = Path(p)
        return str(path if path.is_absolute() else base_dir / path)

    try:
        kwargs = {
            "access_key": cfg.access_key,
            "keyword_paths": [_abs(cfg.wake_word_ppn_path)],
        }
        # 中文模型 .pv 不一定每平台都需要 (SDK 內附 default)、若存在用 Edward 指定的
        if ready["zh_model_exists"]:
            kwargs["model_path"] = _abs(cfg.chinese_model_pv_path)
        return pvporcupine.create(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning("Porcupine init 失敗 (%s)、wake word OFF", str(e)[:100])
        return None


def init_eagle_recognizer(cfg: Optional[PicovoiceConfig] = None):
    """
    建立 Eagle voice ID recognizer。

    Edward 必須先做完:
      1. 申請 AccessKey
      2. 跑 breeze_poc/register_eagle_speaker.py 註冊聲紋 → 產出 .bin

    Returns:
        eagle instance 或 None
    """
    pveagle = _lazy_import_eagle()
    if pveagle is None:
        logger.info("pveagle 未安裝、voice ID OFF")
        return None

    if cfg is None:
        cfg = PicovoiceConfig.from_env()

    ready = is_picovoice_ready(cfg)
    if not ready["access_key_set"]:
        logger.info("PICOVOICE_ACCESS_KEY 沒設、voice ID OFF")
        return None
    if not ready["eagle_profile_exists"]:
        logger.info(
            "Eagle profile .bin 不存在 (path: %s)、voice ID OFF (Edward 跑 register_eagle_speaker.py 註冊)",
            cfg.eagle_profile_path,
        )
        return None

    base_dir = Path(__file__).resolve().parent.parent.parent

    def _abs(p: str) -> str:
        path = Path(p)
        return str(path if path.is_absolute() else base_dir / path)

    try:
        with open(_abs(cfg.eagle_profile_path), "rb") as fh:
            profile_bytes = fh.read()
        profile = pveagle.EagleProfile.from_bytes(profile_bytes)
        return pveagle.create_recognizer(
            access_key=cfg.access_key,
            speaker_profiles=[profile],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Eagle init 失敗 (%s)、voice ID OFF", str(e)[:100])
        return None
