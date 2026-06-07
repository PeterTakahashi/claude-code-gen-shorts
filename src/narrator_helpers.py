"""TTS primitives — Aivis (VOICEVOX-compatible) backend.

`synthesize` is the single entry point used by `narrate.py`. It takes a speaker
style_id (integer) — see project.voice_for() for the lookup.

`to_hiragana` is preserved for the M5 lexicon-correction layer; M2 doesn't use
it because Aivis handles kanji natively via pyopenjtalk.
"""
from __future__ import annotations

from pathlib import Path

from pykakasi import kakasi

from .aivis import AivisClient, default_client


_KKS = kakasi()


def to_hiragana(text: str) -> str:
    """Convert mixed Japanese (kanji+kana) into all-hiragana.

    Currently unused in the synthesis path (Aivis reads kanji via pyopenjtalk).
    Kept for the M5 lexicon-correction layer.
    """
    parts = _KKS.convert(text)
    return "".join(p["hira"] for p in parts)


def synthesize(
    text: str,
    out_path: Path,
    voice: int,
    *,
    speed: float = 1.0,
    pitch: float = 0.0,
    intonation: float = 1.0,
    client: AivisClient | None = None,
) -> Path:
    """Synthesize one utterance via Aivis.

    `voice` is the Aivis speaker style_id (integer). Output suffix decides format
    (.wav passthrough, .mp3/.m4a → ffmpeg transcode).
    """
    cli = client or default_client()
    return cli.synthesize(text, voice, out_path, speed=speed, pitch=pitch, intonation=intonation)
