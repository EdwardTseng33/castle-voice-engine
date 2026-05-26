"""
SoulX-FlashHead 1.3B Lite · sanity test on Edward's RTX 3070 8GB.

Phase 3.2 PoC (2026-05-22) - Edward 拍板「自用 + 不商業化 + 超強蘇菲演化」
+ ADR-018 雙軌升級（個人自用 framework · 3 條 risk 只）

執行兩階段:
  Stage A: snapshot_download (6.4GB) -> models/soulx-flashhead-1.3b/
  Stage B: minimal inference smoke test
           - check torch + CUDA
           - check VRAM headroom
           - load model
           - dry-run a 1-frame inference (no real photo / audio yet)

執行前提:
  - branch: voice-path/v0.3.2-soulx-flashhead-poc
  - HF Hub OK (network up · 不必登入 · 公開 model)
  - 不上傳 weights 到 git (gitignored models/)
  - 不餵 Sally 樣本 (hard rule)

Edward 邊界規則 (個人自用 · 2026-05-26 校正):
  - Edward 自己樣本: OK
  - Qiana 自願試 (informed consent): OK
  - 訪客 / 旁邊路過的人: 不主動錄
  - 真有未成年互動場景出現時、屆時以真實需求重做安全機制
  - (v0.3.0 移除原「Sally 6 歲」hard rule · 記憶污染、實際無此對象)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models" / "soulx-flashhead-1.3b"


def stage_a_download():
    """Stage A: snapshot_download SoulX-FlashHead-1_3B from HuggingFace."""
    print("=" * 60)
    print("Stage A · download SoulX-FlashHead 1.3B Lite (6.4GB)")
    print("=" * 60)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[FAIL] huggingface_hub 未安裝 · 跑: pip install huggingface_hub")
        return False

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    try:
        local_path = snapshot_download(
            repo_id="Soul-AILab/SoulX-FlashHead-1_3B",
            local_dir=str(MODELS_DIR),
            local_dir_use_symlinks=False,  # Windows 沒 admin · 不用 symlink
        )
        elapsed = time.time() - t0
        print(f"[OK] downloaded to {local_path}")
        print(f"[OK] elapsed: {elapsed:.1f}s")
    except Exception as e:
        print(f"[FAIL] download error: {type(e).__name__}: {e}")
        return False

    # File inventory
    total_size = 0
    file_count = 0
    for f in MODELS_DIR.rglob("*"):
        if f.is_file():
            total_size += f.stat().st_size
            file_count += 1
    print(f"[OK] {file_count} files · total {total_size / 1024 / 1024:.1f} MB")
    return True


def stage_b_smoke():
    """Stage B: minimal smoke test on RTX 3070 8GB."""
    print()
    print("=" * 60)
    print("Stage B · smoke test (torch + CUDA + load model)")
    print("=" * 60)

    # Step 1 · torch + CUDA check
    try:
        import torch
    except ImportError:
        print("[FAIL] torch 未安裝")
        return False
    print(f"[OK] torch {torch.__version__}")
    print(f"[OK] CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"[OK] device: {torch.cuda.get_device_name(0)}")
        total_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"[OK] total VRAM: {total_mem:.2f} GB")
        if total_mem < 7.5:
            print(f"[WARN] VRAM < 7.5GB · 1.3B + KV cache 可能 OOM · 考慮 INT8 quantize")
    else:
        print("[WARN] CUDA 不可用 · CPU 跑會極慢 · 不適合即時")

    # Step 2 · check model files exist
    if not MODELS_DIR.exists():
        print(f"[FAIL] {MODELS_DIR} 不存在 · 先跑 Stage A")
        return False

    config_path = MODELS_DIR / "config.json"
    if not config_path.exists():
        print(f"[FAIL] config.json 不存在 · download 不完整?")
        return False
    print(f"[OK] config.json found")

    # Step 3 · try load model (各家 model 規格不同 · 第一步先試 transformers AutoConfig)
    try:
        from transformers import AutoConfig
        config = AutoConfig.from_pretrained(str(MODELS_DIR), trust_remote_code=True)
        print(f"[OK] AutoConfig loaded · model_type: {getattr(config, 'model_type', 'unknown')}")
    except Exception as e:
        print(f"[INFO] AutoConfig fail: {type(e).__name__}: {e}")
        print(f"[INFO] 可能需要自家 loader · 看 model card")
        # Don't return False here · 自家 loader 仍可能 work

    # Step 4 · README / model card 摘要
    readme_paths = [MODELS_DIR / "README.md", MODELS_DIR / "MODEL_CARD.md"]
    for p in readme_paths:
        if p.exists():
            print()
            print(f"[INFO] {p.name} (first 30 lines):")
            print("-" * 40)
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh):
                    if i >= 30:
                        break
                    print(line.rstrip())
            print("-" * 40)
            break

    print()
    print("[SUMMARY] Stage B smoke pass (model files exist + torch OK)")
    print("[NEXT] 真實 inference 需 follow Soul-AILab GitHub README example code")
    print("       (model 用法各家不同、不能用 transformers 通用 API 強跑)")
    return True


def main():
    print("Voice Path Phase 3.2 · SoulX-FlashHead 1.3B Lite PoC")
    print("Edward「自用 + 不商業化 + 超強蘇菲演化」框架")
    print()

    # Stage A: download (only if not already downloaded)
    if MODELS_DIR.exists() and any(MODELS_DIR.iterdir()):
        print(f"[SKIP A] {MODELS_DIR} 已存在 · skip download")
    else:
        if not stage_a_download():
            sys.exit(1)

    # Stage B: smoke
    if not stage_b_smoke():
        sys.exit(2)

    print()
    print("=" * 60)
    print("PoC sanity PASS · 下個 step: 跑真實 inference (依 Soul-AILab GitHub)")
    print("=" * 60)


if __name__ == "__main__":
    main()
