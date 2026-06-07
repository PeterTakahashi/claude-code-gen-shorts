"""Split bubble text into TTS chunks and display-subtitle chunks.

This module has two distinct splitters that solve two different problems:

1. `split_for_tts(text)` — splits text only at Japanese SENTENCE boundaries
   (`。` / `！` / `？`). Each sentence becomes a single TTS synthesis call,
   so the voice model sees a complete utterance and gives it natural prosody.
   Critically, this does NOT split on `、` (comma) — splitting mid-sentence
   into separate TTS calls causes Aivis to emit "end of sentence" falling
   tone followed by "beginning of sentence" rising tone, which sounds
   choppy and unnatural.

2. `split_for_display(text, max_chars=35)` — within a TTS chunk, splits the
   text into display pieces small enough to fit one subtitle line on a
   1920×1080 video. May split at `、`, particle boundaries, or hard cap.

`narrate.py` calls these in sequence:
  - one synthesize() call per TTS chunk (natural prosody)
  - each TTS chunk's audio duration is distributed proportionally across
    its display pieces by character count
"""
from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 35
DEFAULT_TTS_SOFT_CAP = 250

_SENTENCE_END = re.compile(r"(?<=[。！？])")
_COMMA_END = re.compile(r"(?<=、)")


def _hard_chunk(text: str, max_chars: int) -> list[str]:
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _greedy_merge(parts: list[str], max_chars: int) -> list[str]:
    """Concatenate parts in order while staying ≤ max_chars per output."""
    out: list[str] = []
    cur = ""
    for p in parts:
        if not cur:
            cur = p
            continue
        if len(cur) + len(p) <= max_chars:
            cur += p
        else:
            out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return out


def split_for_tts(text: str, soft_cap: int = DEFAULT_TTS_SOFT_CAP) -> list[str]:
    """Split `text` into TTS chunks at sentence boundaries (`。`/`！`/`？`).

    Never splits at `、`. If a single sentence is unusually long (> soft_cap),
    falls back to comma splitting for THAT sentence only, because Aivis has
    practical limits on single-call length. In normal use the soft_cap is
    rarely hit.
    """
    text = text.strip()
    if not text:
        return []
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
    out: list[str] = []
    for sent in sentences:
        if len(sent) <= soft_cap:
            out.append(sent)
            continue
        # Pathological long sentence — fall back to comma splitting.
        parts = [c.strip() for c in _COMMA_END.split(sent) if c.strip()]
        out.extend(_greedy_merge(parts, soft_cap))
    return out


def split_for_display(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split a TTS chunk's text into display pieces ≤ max_chars.

    Splits at `、` first (preserves the comma in the leading piece),
    falls back to a hard chunk if any single segment still exceeds max_chars.
    Returns at least one piece.
    """
    text = text.strip()
    if not text:
        return [text]
    if len(text) <= max_chars:
        return [text]

    comma_parts = [c for c in _COMMA_END.split(text) if c]
    merged = _greedy_merge(comma_parts, max_chars)

    final: list[str] = []
    for piece in merged:
        if len(piece) <= max_chars:
            final.append(piece)
        else:
            final.extend(_hard_chunk(piece, max_chars))
    return final


# Backwards-compatible aliases (older callers may import these names).
split_text = split_for_display


def split_bubble(bubble: dict, max_chars: int = DEFAULT_MAX_CHARS) -> list[dict]:
    """DEPRECATED — caller should drive TTS + display split itself via
    `split_for_tts` and `split_for_display`. Kept for any old code paths.
    """
    text = (bubble.get("text") or "").strip()
    if len(text) <= max_chars:
        return [bubble]
    chunks = split_for_display(text, max_chars=max_chars)
    out: list[dict] = []
    for ch in chunks:
        new_b = dict(bubble)
        new_b["text"] = ch
        out.append(new_b)
    return out


if __name__ == "__main__":
    sample = "自分は、その薄暗い部屋の末席に、寒さにがたがた震える思いで、口にごはんを少量ずつ運び、押し込んでいた。めしを食べなければ死ぬ、という言葉は、自分の耳には、ただイヤな、おどかしとしか、聞えなかった。"
    print("--- TTS chunks (one synthesis per chunk) ---")
    for c in split_for_tts(sample):
        print(f"[{len(c):3d}] {c}")
    print("\n--- Display pieces per TTS chunk (≤35 char subtitles) ---")
    for c in split_for_tts(sample):
        print(f"  sentence: {c}")
        for d in split_for_display(c):
            print(f"    [{len(d):3d}] {d}")
