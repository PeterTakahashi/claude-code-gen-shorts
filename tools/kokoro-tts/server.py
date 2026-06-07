"""Kokoro-82M HTTP server (single-process, persistent pipeline in memory).

Mirrors the Qwen3-TTS pattern: launch once, hit /synthesize per request.
Kokoro-82M is fully deterministic — no hallucinated laughs / sighs.

Run:
  tools/kokoro-tts/.venv/bin/python tools/kokoro-tts/server.py
  # default: 127.0.0.1:10103 (Aivis=10101, Qwen=10102)

Endpoints:
  GET  /health
  POST /synthesize
      JSON body:
        text:     str
        voice:    e.g. "am_michael" (US male), "bm_lewis" (UK male), "af_heart" (US female), ...
        speed:    float (default 1.0)
        lang:     "a" (American English, default) or "b" (British English)
      Returns: audio/wav (24000 Hz, mono, PCM_16)
"""
from __future__ import annotations

import argparse
import io
import logging
import os

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

REPO_ID = os.environ.get("KOKORO_REPO_ID", "hexgrad/Kokoro-82M")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kokoro-tts-server")

app = FastAPI(title="Kokoro-82M local")

# Cache one pipeline per lang_code ('a' or 'b').
_pipelines: dict[str, "object"] = {}


def get_pipeline(lang: str):
    if lang not in _pipelines:
        from kokoro import KPipeline  # type: ignore
        log.info("loading Kokoro pipeline lang=%s …", lang)
        _pipelines[lang] = KPipeline(lang_code=lang, repo_id=REPO_ID)
        log.info("pipeline loaded lang=%s", lang)
    return _pipelines[lang]


class SynthesizeReq(BaseModel):
    text: str
    voice: str = "am_michael"
    speed: float = 1.0
    lang: str = "a"


@app.get("/health")
def health():
    return {"status": "ok", "loaded_pipelines": list(_pipelines.keys()), "repo": REPO_ID}


@app.post("/synthesize")
def synthesize(req: SynthesizeReq):
    if not req.text.strip():
        raise HTTPException(400, "empty text")
    pipeline = get_pipeline(req.lang)
    log.info("synth: voice=%s lang=%s speed=%.2f text=%r",
             req.voice, req.lang, req.speed, req.text[:80])
    try:
        chunks: list[torch.Tensor] = []
        for _, _, audio in pipeline(req.text, voice=req.voice, speed=req.speed):
            chunks.append(audio if isinstance(audio, torch.Tensor) else torch.as_tensor(audio))
        wav = torch.cat(chunks).cpu().numpy()
    except Exception as e:
        log.exception("generation failed")
        raise HTTPException(500, f"kokoro error: {e}")

    buf = io.BytesIO()
    sf.write(buf, wav, 24000, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav",
                    headers={"X-Sample-Rate": "24000", "X-Voice": req.voice})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=10103)
    p.add_argument("--warm", action="store_true",
                   help="Load the 'a' (American English) pipeline on startup.")
    args = p.parse_args()
    if args.warm:
        get_pipeline("a")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
