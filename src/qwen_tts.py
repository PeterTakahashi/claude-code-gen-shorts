"""Client for the local Qwen3-TTS HTTP server (tools/qwen-tts/server.py).

Mirrors the Aivis client API for parallel substitution.

Server lifecycle:
  start:  tools/qwen-tts/.venv/bin/python tools/qwen-tts/server.py --warm
  health: GET http://127.0.0.1:10102/health

Speakers (English voices baked into the CustomVoice 1.7B model):
  - Ryan  : dynamic male voice with strong rhythmic drive
  - Aiden : sunny American male voice with a clear midrange
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

DEFAULT_ENDPOINT = os.environ.get("QWEN_TTS_ENDPOINT", "http://127.0.0.1:10102")
DEFAULT_SPEAKER = os.environ.get("QWEN_TTS_SPEAKER", "Ryan")


class QwenTTSError(RuntimeError):
    pass


class QwenTTSClient:
    def __init__(self, endpoint: str | None = None, timeout: float = 600.0):
        self.endpoint = (endpoint or DEFAULT_ENDPOINT).rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def health(self) -> dict:
        r = self._client.get(f"{self.endpoint}/health")
        r.raise_for_status()
        return r.json()

    def synthesize(
        self,
        text: str,
        out_path: Path,
        *,
        speaker: str = DEFAULT_SPEAKER,
        language: str = "English",
    ) -> Path:
        """Synthesize one utterance to a WAV file at out_path.
        If out_path ends in .mp3 it is transcoded via ffmpeg.
        """
        r = self._client.post(
            f"{self.endpoint}/synthesize",
            json={"text": text, "speaker": speaker, "language": language},
        )
        if r.status_code != 200:
            raise QwenTTSError(f"{r.status_code}: {r.text[:400]}")
        wav_bytes = r.content

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".wav":
            out_path.write_bytes(wav_bytes)
            return out_path

        # Transcode to mp3 (or whatever) via ffmpeg
        import subprocess
        tmp_wav = out_path.with_suffix(".tmp.wav")
        tmp_wav.write_bytes(wav_bytes)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(tmp_wav), "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)],
                check=True, capture_output=True,
            )
        finally:
            tmp_wav.unlink(missing_ok=True)
        return out_path

    def close(self) -> None:
        self._client.close()


_DEFAULT: QwenTTSClient | None = None


def default_client() -> QwenTTSClient:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = QwenTTSClient()
    return _DEFAULT


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--speaker", default="Ryan")
    p.add_argument("--language", default="English")
    args = p.parse_args()

    c = default_client()
    info = c.health()
    print(f"server: {info}")
    out = c.synthesize(args.text, args.out, speaker=args.speaker, language=args.language)
    print(f"wrote: {out}")
