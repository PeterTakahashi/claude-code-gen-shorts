"""Qwen3-TTS HTTP server (single-process, persistent model in memory).

Mirrors the Aivis pattern: launch once, hit /synthesize for each request.
Avoids the 96-second per-call model load cost.

Run:
  tools/qwen-tts/.venv/bin/python tools/qwen-tts/server.py
  # default: 127.0.0.1:10102 (Aivis uses :10101)

Endpoints:
  GET  /health
  POST /synthesize
      JSON body:
        text:     str
        speaker:  "Ryan" | "Aiden"   (default Ryan)
        language: "English"            (default English; Qwen3-TTS supports 10 langs)
      Returns: audio/wav (24000 Hz, mono, float32 PCM in wav container)

Notes:
  - Loads the model lazily on first request (warm-up ~90s)
  - Generation is ~3x realtime on M-series MPS bfloat16
"""
from __future__ import annotations

import argparse
import io
import logging
import os
from typing import Optional

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

MODEL_NAME = os.environ.get("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
DEVICE = os.environ.get("QWEN_TTS_DEVICE", "mps")
DTYPE_NAME = os.environ.get("QWEN_TTS_DTYPE", "bfloat16")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("qwen-tts-server")

app = FastAPI(title="Qwen3-TTS local")

_model = None


def _dtype():
    return {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[DTYPE_NAME]


def get_model():
    global _model
    if _model is None:
        from qwen_tts import Qwen3TTSModel  # type: ignore
        log.info("loading %s on %s / dtype=%s …", MODEL_NAME, DEVICE, DTYPE_NAME)
        _model = Qwen3TTSModel.from_pretrained(MODEL_NAME, device_map=DEVICE, dtype=_dtype())
        log.info("model loaded")
    return _model


class SynthesizeReq(BaseModel):
    text: str
    speaker: str = "Ryan"
    language: str = "English"


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _model is not None,
            "model": MODEL_NAME, "device": DEVICE, "dtype": DTYPE_NAME}


@app.post("/synthesize")
def synthesize(req: SynthesizeReq):
    if not req.text.strip():
        raise HTTPException(400, "empty text")
    model = get_model()
    log.info("synth: speaker=%s lang=%s text=%r", req.speaker, req.language, req.text[:80])
    try:
        wavs, sr = model.generate_custom_voice(
            text=req.text,
            language=req.language,
            speaker=req.speaker,
        )
    except Exception as e:
        log.exception("generation failed")
        raise HTTPException(500, f"qwen3-tts error: {e}")
    buf = io.BytesIO()
    sf.write(buf, wavs[0], sr, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav",
                    headers={"X-Sample-Rate": str(sr), "X-Speaker": req.speaker})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=10102)
    p.add_argument("--warm", action="store_true", help="Load model on startup instead of first request")
    args = p.parse_args()
    if args.warm:
        get_model()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
