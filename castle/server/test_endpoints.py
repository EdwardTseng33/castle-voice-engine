# castle-voice-engine - (c) 2026 Edward / BeyondPath
# Built on PersonaPlex (NVIDIA, NOML) and Moshi (Kyutai, MIT)
# castle/server/test_endpoints.py - v0.1.1 verification harness.
# DEPRECATED v0.1.5 (2026-04-27) - PersonaPlex 7B confirmed OOD on system
# prompt steering during Edward audit; voice backend swapped to OpenAI Realtime
# API (see castle/server/realtime_endpoints.py). This file is kept on disk as
# a reference archive but is NOT attached to app.py and its torch/moshi imports
# WILL fail at runtime - those deps were removed from requirements.txt.
# Do not re-attach without re-installing the PersonaPlex stack.
#

from __future__ import annotations
import io, os, tarfile, traceback
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

_pp_model_cache = {"loaded": False, "error": None}

# HTML page served at GET /test - inline minimal Chinese audition UI
HTML_PAGE = '''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Castle Voice Engine</title>
<style>
:root{--bg:#f7f4ee;--ink:#2a2622;--accent:#8a5a3c;--line:#d6cfc4;--warn:#b85c2e;--ok:#4a7a3c}
*{box-sizing:border-box}
body{margin:0;padding:24px;font-family:Georgia,"Noto Serif TC",serif;background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{max-width:640px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px;font-style:italic}
.sub{color:#7a6f64;font-size:13px;margin-bottom:24px}
.card{background:#fff;border:1px solid var(--line);border-radius:6px;padding:20px;margin-bottom:16px}
label{display:block;font-size:13px;color:#5a5048;margin-bottom:6px;font-weight:600}
.voices{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}
.voices label:has(input:checked){background:#f0e6d8;border-color:var(--accent)}
.voices label{display:flex;align-items:center;gap:6px;font-weight:400;padding:8px 10px;border:1px solid var(--line);border-radius:4px;cursor:pointer;background:#fafafa}
textarea{width:100%;min-height:80px;padding:10px;font-family:inherit;font-size:15px;border:1px solid var(--line);border-radius:4px;resize:vertical}
button{margin-top:12px;padding:10px 18px;font-size:15px;background:var(--accent);color:#fff;border:0;border-radius:4px;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
.status{margin-top:16px;padding:10px;font-size:13px;min-height:20px}
.status.loading{color:#7a6f64}
.status.warn{color:var(--warn)}
.status.ok{color:var(--ok)}
audio{width:100%;margin-top:12px}
pre.diag{background:#2a2622;color:#f0e6d8;padding:10px;font-size:11px;border-radius:4px;overflow-x:auto;margin-top:12px;white-space:pre-wrap;word-break:break-all}
.footnote{font-size:11px;color:#9a8f84;margin-top:24px;text-align:center}
</style></head><body><div class="wrap">
<h1>Castle Voice Engine</h1>
<div class="sub">中文試聽 - PersonaPlex 7B (NATF/NATM voice library)</div>
<div class="card">
<label>Voice preset</label>
<div class="voices">
<label><input type="radio" name="v" value="NATF1" checked>NATF1 自然女聲 1</label>
<label><input type="radio" name="v" value="NATF2">NATF2 自然女聲 2</label>
<label><input type="radio" name="v" value="NATF3">NATF3 自然女聲 3</label>
<label><input type="radio" name="v" value="NATM1">NATM1 自然男聲 1</label>
<label><input type="radio" name="v" value="NATM2">NATM2 自然男聲 2</label>
<label><input type="radio" name="v" value="NATM3">NATM3 自然男聲 3</label>
</div>
<label>說話內容（中文）</label>
<textarea id="text">你好，我是蘇菲，今天怎麼了？</textarea>
<button id="go">▶ 試聽</button>
<div id="status" class="status"></div>
<audio id="audio" controls style="display:none"></audio>
<pre id="diag" class="diag" style="display:none"></pre>
</div>
<div class="footnote">castle-voice-engine v0.1.1 - PersonaPlex 7B (NVIDIA NOML) + Moshi (Kyutai MIT)</div>
</div>
<script>
(function(){
const btn=document.getElementById("go");
const statusEl=document.getElementById("status");
const audio=document.getElementById("audio");
const diag=document.getElementById("diag");
btn.addEventListener("click", async () => {
  const voice=document.querySelector('input[name="v"]:checked').value;
  const txt=document.getElementById("text").value.trim();
  if(!txt){statusEl.className="status warn";statusEl.textContent="請先輸入文字";return;}
  btn.disabled=true; audio.style.display="none"; diag.style.display="none";
  statusEl.className="status loading";
  statusEl.textContent="● 載入中…首次呼叫含 cold start (5-8 min download 14GB model)";
  try{
    const r=await fetch("/test/synthesize",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({voice_preset:voice,text:txt})});
    if(!r.ok){const e=await r.text(); statusEl.className="status warn"; statusEl.textContent="失敗 "+r.status; diag.style.display="block"; diag.textContent=e; return;}
    const dh=r.headers.get("X-CVE-Diagnostics");
    const bl=await r.blob();
    audio.src=URL.createObjectURL(bl); audio.style.display="block";
    statusEl.className="status ok"; statusEl.textContent="✓ 完成 — 點 ▶ 播放";
    if(dh){diag.style.display="block"; diag.textContent="diagnostics: "+dh;}
    audio.play().catch(()=>{});
  }catch(e){statusEl.className="status warn"; statusEl.textContent="錯誤："+e.message;}
  finally{btn.disabled=false;}
});
})();
</script>
</body></html>'''



class SynthesizeRequest(BaseModel):
    voice_preset: str = "NATF1"
    text: str


def _load_personaplex_once():
    """Lazy load PersonaPlex pipeline once per container. Returns (ok, error_msg)."""
    if _pp_model_cache.get("loaded"):
        return True, None
    if _pp_model_cache.get("error"):
        return False, _pp_model_cache["error"]
    try:
        import torch
        from huggingface_hub import hf_hub_download
        from moshi.models import loaders
        import sentencepiece

        device = "cuda" if torch.cuda.is_available() else "cpu"
        hf_repo = "nvidia/personaplex-7b-v1"

        hf_hub_download(hf_repo, "config.json", cache_dir="/cache/personaplex")
        mimi_weight = hf_hub_download(hf_repo, loaders.MIMI_NAME, cache_dir="/cache/personaplex")
        mimi = loaders.get_mimi(mimi_weight, device)
        other_mimi = loaders.get_mimi(mimi_weight, device)
        tok_path = hf_hub_download(hf_repo, loaders.TEXT_TOKENIZER_NAME, cache_dir="/cache/personaplex")
        text_tokenizer = sentencepiece.SentencePieceProcessor(tok_path)
        moshi_weight = hf_hub_download(hf_repo, loaders.MOSHI_NAME, cache_dir="/cache/personaplex")
        lm = loaders.get_moshi_lm(moshi_weight, device=device, cpu_offload=False)
        lm.eval()

        voices_tgz = hf_hub_download(hf_repo, "voices.tgz", cache_dir="/cache/personaplex")
        voices_dir = Path(voices_tgz).parent / "voices"
        if not voices_dir.exists():
            with tarfile.open(voices_tgz, "r:gz") as tar:
                tar.extractall(path=Path(voices_tgz).parent)

        _pp_model_cache.update({
            "loaded": True,
            "device": device,
            "mimi": mimi,
            "other_mimi": other_mimi,
            "text_tokenizer": text_tokenizer,
            "lm": lm,
            "voices_dir": str(voices_dir),
            "frame_size": int(mimi.sample_rate / mimi.frame_rate),
            "sample_rate": int(mimi.sample_rate),
        })
        return True, None
    except Exception as e:
        msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _pp_model_cache["error"] = msg
        return False, msg


def _run_personaplex_inference(voice_preset, text):
    """Run PersonaPlex offline-style inference. Returns (wav_bytes, diagnostics).

    PersonaPlex is speech-to-speech, not pure TTS. Strategy: feed silence as
    user input + bias system prompt toward Mandarin output. If model can speak
    Chinese at all, this surfaces it; if not, returns silence/English fallback
    that Edward can audit.
    """
    import numpy as np
    import torch
    import soundfile as sf
    from moshi.models import LMGen

    cache = _pp_model_cache
    mimi = cache["mimi"]
    other_mimi = cache["other_mimi"]
    text_tokenizer = cache["text_tokenizer"]
    lm = cache["lm"]
    device = cache["device"]
    sample_rate = cache["sample_rate"]
    frame_size = cache["frame_size"]
    voices_dir = cache["voices_dir"]

    voice_prompt_path = os.path.join(voices_dir, f"{voice_preset}.pt")
    if not os.path.exists(voice_prompt_path):
        raise HTTPException(status_code=400, detail=f"voice preset {voice_preset!r} not found")

    lm_gen = LMGen(
        lm,
        audio_silence_frame_cnt=int(0.5 * mimi.frame_rate),
        sample_rate=mimi.sample_rate,
        device=device,
        frame_rate=mimi.frame_rate,
        save_voice_prompt_embeddings=False,
        use_sampling=True,
        temp=0.8,
        temp_text=0.7,
        top_k=250,
        top_k_text=25,
    )
    mimi.streaming_forever(1)
    other_mimi.streaming_forever(1)
    lm_gen.streaming_forever(1)

    lm_gen.load_voice_prompt_embeddings(voice_prompt_path)

    system_prompt = (
        "You enjoy having a good conversation. "
        "Please respond in Traditional Chinese (Taiwan). "
        f"The user said: {text}. Reply naturally in Mandarin."
    )
    wrapped = f"<system> {system_prompt} <system>"
    lm_gen.text_prompt_tokens = text_tokenizer.encode(wrapped)

    mimi.reset_streaming()
    other_mimi.reset_streaming()
    lm_gen.reset_streaming()

    # NOTE: step_system_prompts requires the mimi instance (used to encode the
    # voice-prompt audio internally). After this we reset mimi's streaming state
    # so the user-side input begins fresh.
    lm_gen.step_system_prompts(mimi)
    mimi.reset_streaming()

    target_frames = int(5 * mimi.frame_rate)
    out_pcm_chunks = []

    with torch.no_grad():
        for _ in range(target_frames):
            silence = torch.zeros(1, 1, frame_size, dtype=torch.float32, device=device)
            codes = mimi.encode(silence)
            _ = other_mimi.encode(silence)
            for c in range(codes.shape[-1]):
                tokens = lm_gen.step(codes[:, :, c:c+1])
                if tokens is None:
                    continue
                pcm = mimi.decode(tokens[:, 1:9])
                _ = other_mimi.decode(tokens[:, 1:9])
                out_pcm_chunks.append(pcm.detach().cpu().numpy()[0, 0])

    if not out_pcm_chunks:
        raise RuntimeError("PersonaPlex produced no audio frames")

    audio = np.concatenate(out_pcm_chunks).astype(np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)
    diagnostics = (
        f"voice={voice_preset} text_len={len(text)} "
        f"out_samples={len(audio)} sr={sample_rate} "
        f"duration={len(audio)/sample_rate:.2f}s"
    )
    return buf.read(), diagnostics


def attach_test_routes(app: FastAPI) -> None:
    """Attach /test page + /test/synthesize POST onto an existing FastAPI instance."""

    @app.get("/test", response_class=HTMLResponse)
    async def test_page():
        return HTMLResponse(content=HTML_PAGE)

    @app.post("/test/synthesize")
    async def test_synthesize(req: SynthesizeRequest):
        ok, err = _load_personaplex_once()
        if not ok:
            return JSONResponse(
                status_code=503,
                content={"error": "PersonaPlex model load failed", "detail": err},
            )
        try:
            wav_bytes, diagnostics = _run_personaplex_inference(req.voice_preset, req.text)
        except HTTPException:
            raise
        except Exception as e:
            tb = traceback.format_exc()
            return JSONResponse(
                status_code=500,
                content={"error": "inference_failed", "detail": f"{type(e).__name__}: {e}", "traceback": tb},
            )
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"X-CVE-Diagnostics": diagnostics},
        )
