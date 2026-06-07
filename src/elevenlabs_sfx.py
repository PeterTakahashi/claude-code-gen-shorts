"""ElevenLabs Sound Generation client — generates SFX mp3 from a text prompt.

Used by short_gen.py to add a 5-second SFX at the start of each short,
mixed under the narration at low volume to boost watch-time.

API docs: https://api.elevenlabs.io/docs#tag/Sound-Effects/operation/Generate-sound-effects
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx

ENDPOINT = "https://api.elevenlabs.io/v1/sound-generation"


class ElevenLabsSFXError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("ELEVEN_LABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise ElevenLabsSFXError("ELEVEN_LABS_API_KEY not set in env")
    return key


def generate_sfx(prompt: str, out_path: Path, *, duration_seconds: float = 5.0,
                 prompt_influence: float = 0.5, timeout: float = 60.0) -> Path:
    """Generate an SFX mp3 from a text prompt. Caches by prompt+duration hash.

    The cache lives at out_path.parent / .sfx_cache / <sha1>.mp3 — if a file
    exists, copy it to out_path instead of re-calling the API. This means
    re-running a build with the same SFX prompt costs $0.
    """
    cache_dir = out_path.parent / ".sfx_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha1(f"{prompt}|{duration_seconds}|{prompt_influence}".encode()).hexdigest()[:16]
    cache_file = cache_dir / f"{cache_key}.mp3"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_file.exists():
        out_path.write_bytes(cache_file.read_bytes())
        return out_path

    headers = {"xi-api-key": _api_key(), "Content-Type": "application/json"}
    body = {
        "text": prompt,
        "duration_seconds": float(duration_seconds),
        "prompt_influence": float(prompt_influence),
    }
    with httpx.Client(timeout=timeout) as c:
        r = c.post(ENDPOINT, json=body, headers=headers)
    if r.status_code != 200:
        raise ElevenLabsSFXError(f"{r.status_code}: {r.text[:400]}")

    cache_file.write_bytes(r.content)
    out_path.write_bytes(r.content)
    return out_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--duration", type=float, default=5.0)
    args = p.parse_args()
    out = generate_sfx(args.prompt, args.out, duration_seconds=args.duration)
    print(f"wrote {out}  ({out.stat().st_size} bytes)")
