# castle-voice-engine / castle/server/lipsync_match_endpoint.py
# (c) 2026 Edward / BeyondPath
#
# v0.4.x (2026-05-28): 意思向量比對 endpoint (取代純 Levenshtein 字面比對)
#
# 為什麼:
#   舊 phrase-matcher.js 用 Levenshtein 字面距離 → ratio < 0.30 = 命中
#   問題: 「Edward 早 今天怎樣」跟「早安 Edward 新的一天」字面距離大、意思一樣、不命中
#   解: 把句子轉成意思向量 (OpenAI text-embedding-3-small)、比向量 cosine similarity
#
# 架構:
#   - 啟動時 lazy-load 100 句 manifest、為每句算一次 embedding、存 in-memory
#   - 收到 transcript chunk → embedding chunk → cosine 比 100 句 → 回最近 + 分數
#   - threshold > 0.55 = 命中 (空間調過後)
#   - cache: 同一個 transcript 文字不重複算 embedding
#
# 成本:
#   - text-embedding-3-small: $0.02 / 1M tokens
#   - 100 句啟動 embedding: < 5000 tokens ≈ $0.0001 (一次性)
#   - 即時對話: 每 chunk ~30 tokens ≈ $0.0000006 / chunk
#   - 月度 cap: 1 萬次比對 ≈ $0.006

# NOTE: 故意不用 `from __future__ import annotations` ·
#       此 module attach_lipsync_match_routes 內走 @app.post + `request: Request` ·
#       未來 annotation 模式會讓 FastAPI 在 closure 內 resolve Request 失敗 (整段 endpoint 404/405)
import os
import json
import time
import logging
import math
from typing import List, Dict, Any, Optional
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("castle.lipsync_match")

# in-memory state (process-local · Modal scale-down 重置)
_phrase_embeddings: Optional[List[Dict[str, Any]]] = None  # [{phrase_id, sentence, mp4_url, embedding}]
_query_cache: Dict[str, List[float]] = {}  # transcript -> embedding (LRU 1000 entries)
_query_cache_order: List[str] = []
_MAX_CACHE = 1000

# threshold · OpenAI text-embedding-3-small cosine score
# > 0.55 = 大致同義 / 0.45-0.55 = 模糊接近 / < 0.45 = 不算命中
SIMILARITY_THRESHOLD = float(os.environ.get("LIPSYNC_MATCH_THRESHOLD", "0.55"))


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(len(a)):
        dot += a[i] * b[i]
        na += a[i] * a[i]
        nb += b[i] * b[i]
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _normalize(s: str) -> str:
    """match the front-end normalize: strip punctuation + spaces + lowercase"""
    if not s or not isinstance(s, str):
        return ""
    out = []
    skip = set("，。！？、・·~～ \t\n\r!?.,:;-")
    for ch in s:
        if ch in skip:
            continue
        out.append(ch)
    return "".join(out).lower()


def _embed_one(client, text: str) -> List[float]:
    """call OpenAI text-embedding-3-small for a single string"""
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return resp.data[0].embedding


def _query_embedding(client, text: str) -> List[float]:
    """get query embedding with LRU cache"""
    key = _normalize(text)
    if not key:
        return []
    if key in _query_cache:
        # bump LRU
        try:
            _query_cache_order.remove(key)
        except ValueError:
            pass
        _query_cache_order.append(key)
        return _query_cache[key]
    emb = _embed_one(client, key)
    _query_cache[key] = emb
    _query_cache_order.append(key)
    while len(_query_cache_order) > _MAX_CACHE:
        old = _query_cache_order.pop(0)
        _query_cache.pop(old, None)
    return emb


def _load_manifest(lipsync_dir: str) -> List[Dict[str, Any]]:
    mf = f"{lipsync_dir}/manifest.json"
    if not os.path.exists(mf):
        logger.warning("[lipsync_match] manifest not found: %s", mf)
        return []
    try:
        with open(mf, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("phrases", []) or []
    except Exception as e:
        logger.exception("[lipsync_match] manifest load fail: %s", str(e))
        return []


def _ensure_phrase_embeddings(client, lipsync_dir: str) -> List[Dict[str, Any]]:
    """lazy init: compute embeddings for all 100 phrases on first request"""
    global _phrase_embeddings
    if _phrase_embeddings is not None:
        return _phrase_embeddings
    phrases = _load_manifest(lipsync_dir)
    if not phrases:
        _phrase_embeddings = []
        return _phrase_embeddings

    logger.info("[lipsync_match] computing embeddings for %d phrases (one-time)", len(phrases))
    t0 = time.time()
    # batch: OpenAI accepts up to 2048 inputs per call · we have <500
    sentences = [_normalize(p.get("sentence", "")) for p in phrases]
    # skip empty
    sentences = [s if s else "_" for s in sentences]
    try:
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=sentences,
        )
        results = []
        for i, p in enumerate(phrases):
            results.append({
                "phrase_id": p.get("phrase_id"),
                "sentence": p.get("sentence", ""),
                "mp4_url": p.get("mp4_url"),
                "embedding": resp.data[i].embedding,
            })
        _phrase_embeddings = results
        logger.info("[lipsync_match] embeddings ready · %d phrases · %.2fs", len(results), time.time() - t0)
    except Exception as e:
        logger.exception("[lipsync_match] batch embedding fail: %s", str(e))
        _phrase_embeddings = []
    return _phrase_embeddings


def attach_lipsync_match_routes(app, lipsync_dir: str = "/lipsync_cache", lipsync_volume=None):
    """Mount /lipsync/match endpoint + /lipsync/match/health."""

    @app.post("/lipsync/match")
    async def lipsync_match(request: Request):
        # 1. parse body
        try:
            body = await request.json()
        except Exception as e:
            return JSONResponse({"ok": False, "error": "bad_body", "detail": str(e)[:200]}, status_code=400)
        text = body.get("text", "")
        if not text or not isinstance(text, str):
            return JSONResponse({"ok": False, "error": "no_text"}, status_code=400)

        # 2. reload volume so newly-added phrase files are visible
        if lipsync_volume is not None:
            try:
                lipsync_volume.reload()
            except Exception:
                pass

        # 3. get OpenAI client
        try:
            from openai import OpenAI
        except ImportError:
            return JSONResponse({"ok": False, "error": "openai_sdk_missing"}, status_code=503)
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not openai_key:
            return JSONResponse({"ok": False, "error": "no_openai_key"}, status_code=503)
        client = OpenAI(api_key=openai_key)

        # 4. ensure phrase embeddings loaded
        phrase_embs = _ensure_phrase_embeddings(client, lipsync_dir)
        if not phrase_embs:
            return JSONResponse({"ok": True, "match": None, "detail": "no_phrases"})

        # 5. embed query (with cache)
        t0 = time.time()
        try:
            q_emb = _query_embedding(client, text)
        except Exception as e:
            logger.exception("[lipsync_match] query embed fail: %s", str(e))
            return JSONResponse({"ok": False, "error": "embed_fail", "detail": str(e)[:200]}, status_code=502)
        if not q_emb:
            return JSONResponse({"ok": True, "match": None, "detail": "empty_query"})

        # 6. cosine vs all phrases · find best
        best = None
        best_score = -1.0
        for p in phrase_embs:
            score = _cosine(q_emb, p["embedding"])
            if score > best_score:
                best_score = score
                best = p

        latency_ms = round((time.time() - t0) * 1000, 1)
        hit = best is not None and best_score >= SIMILARITY_THRESHOLD

        result = {
            "ok": True,
            "match": None,
            "best_score": round(best_score, 4),
            "threshold": SIMILARITY_THRESHOLD,
            "latency_ms": latency_ms,
            "cache_size": len(_query_cache),
        }
        if hit and best is not None:
            result["match"] = {
                "phrase_id": best["phrase_id"],
                "sentence": best["sentence"],
                "mp4_url": best["mp4_url"],
                "score": round(best_score, 4),
            }
        return result

    @app.get("/lipsync/match/health")
    async def lipsync_match_health():
        return {
            "ok": True,
            "phrases_loaded": len(_phrase_embeddings) if _phrase_embeddings is not None else 0,
            "cache_size": len(_query_cache),
            "threshold": SIMILARITY_THRESHOLD,
            "model": "text-embedding-3-small",
        }
