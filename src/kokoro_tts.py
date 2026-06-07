"""Client for the local Kokoro-82M HTTP server (tools/kokoro-tts/server.py).

Mirrors the Aivis / Qwen3-TTS client API for parallel substitution.

Server lifecycle:
  start:  tools/kokoro-tts/start.sh
  health: GET http://127.0.0.1:10103/health

Voices (American English, lang='a'):
  am_michael, am_eric, am_fenrir, am_liam, am_onyx, am_puck, am_adam, am_echo
  af_heart, af_bella, af_nicole, af_aoede, af_sky, af_sarah, af_kore, af_jessica

Voices (British English, lang='b'):
  bm_george, bm_lewis, bm_daniel, bm_fable
  bf_emma, bf_isabella, bf_alice, bf_lily
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx

DEFAULT_ENDPOINT = os.environ.get("KOKORO_TTS_ENDPOINT", "http://127.0.0.1:10103")
DEFAULT_VOICE = os.environ.get("KOKORO_TTS_VOICE", "am_michael")
DEFAULT_LANG = os.environ.get("KOKORO_TTS_LANG", "a")  # 'a' = American, 'b' = British


class KokoroTTSError(RuntimeError):
    pass


class KokoroTTSClient:
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
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        lang: str = DEFAULT_LANG,
    ) -> Path:
        """Synthesize one utterance. WAV stays raw; .mp3 is transcoded via ffmpeg."""
        r = self._client.post(
            f"{self.endpoint}/synthesize",
            json={"text": text, "voice": voice, "speed": speed, "lang": lang},
        )
        if r.status_code != 200:
            raise KokoroTTSError(f"{r.status_code}: {r.text[:400]}")
        wav_bytes = r.content

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".wav":
            out_path.write_bytes(wav_bytes)
            return out_path

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


_DEFAULT: KokoroTTSClient | None = None


def default_client() -> KokoroTTSClient:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = KokoroTTSClient()
    return _DEFAULT


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--voice", default="am_michael")
    p.add_argument("--lang", default="a")
    p.add_argument("--speed", type=float, default=1.0)
    args = p.parse_args()

    c = default_client()
    print(f"server: {c.health()}")
    out = c.synthesize(args.text, args.out, voice=args.voice, speed=args.speed, lang=args.lang)
    print(f"wrote: {out}")
