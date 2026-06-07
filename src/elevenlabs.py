"""ElevenLabs Sound Effects API client.

Endpoint: https://api.elevenlabs.io/v1/sound-generation
Reads ELEVEN_LABS_API_KEY (preferred) or ELEVENLABS_API_KEY from env.

Quirks:
- duration_seconds bounded to [0.5, 22.0]; pass None to let the model decide
- prompt_influence in [0.0, 1.0] (default 0.3) — higher follows the prompt
  more literally, lower lets the model improvise
- response is a single mp3 stream (configurable via output_format)
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


load_dotenv(override=True)

API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
SFX_MAX_DURATION_S = 22.0
SFX_MIN_DURATION_S = 0.5


class ElevenLabsError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("ELEVEN_LABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise ElevenLabsError(
            "ELEVEN_LABS_API_KEY not set in env (.env). "
            "Get one from https://elevenlabs.io and add it to .env."
        )
    return key


def generate_sound_effect(
    prompt: str,
    out_path: Path,
    *,
    duration_seconds: float | None = None,
    prompt_influence: float = 0.3,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    timeout_s: float = 60.0,
) -> Path:
    """Generate a single SFX clip and save it to `out_path` (mp3).

    `duration_seconds`:
      - None → model picks
      - <0.5 → clamped to 0.5
      - >22 → clamped to 22 (use generate_looped_bgm() for longer ambience)
    """
    body: dict = {
        "text": prompt,
        "prompt_influence": float(prompt_influence),
        "output_format": output_format,
    }
    if duration_seconds is not None:
        d = max(SFX_MIN_DURATION_S, min(SFX_MAX_DURATION_S, float(duration_seconds)))
        body["duration_seconds"] = d

    headers = {
        "xi-api-key": _api_key(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    url = f"{API_BASE}/sound-generation"
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, json=body, headers=headers)
        if r.status_code >= 400:
            raise ElevenLabsError(f"sound-generation failed [{r.status_code}]: {r.text[:500]}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(r.content)
    return out_path
