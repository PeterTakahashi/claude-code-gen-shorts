"""Reading-correction lexicon (layer 1 of Aivis kanji control).

projects/<id>/lexicon.yaml shape:
  words:
    - { surface: 葉蔵,   reading: ようぞう, kind: name }
    - { surface: 大庭,   reading: おおば,   kind: name }
    - { surface: 円タク, reading: えんたく, kind: noun }

`Lexicon.apply(text)` replaces each surface with its hiragana reading. This
runs *before* the text is sent to Aivis. Aivis still does its own G2P; this
just pins specific words that pyopenjtalk gets wrong.

Layer 2 (audio_query mora editing) is reserved for a future expansion.
Layer 3 (Whisper verification) lives in `src/voice_verify.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LexiconWord:
    surface: str
    reading: str          # hiragana
    kind: str = "noun"    # name | place | noun | verb | …


@dataclass
class Lexicon:
    words: list[LexiconWord] = field(default_factory=list)
    _pattern: re.Pattern[str] | None = None

    def __post_init__(self) -> None:
        self._build_pattern()

    def _build_pattern(self) -> None:
        if not self.words:
            self._pattern = None
            return
        # Sort by length descending so longer surfaces win when a shorter one
        # is a prefix (e.g., 葉蔵 before 葉).
        sorted_words = sorted(self.words, key=lambda w: -len(w.surface))
        alts = "|".join(re.escape(w.surface) for w in sorted_words)
        self._pattern = re.compile(alts)
        self._lookup: dict[str, str] = {w.surface: w.reading for w in self.words}

    def apply(self, text: str) -> str:
        if not text or self._pattern is None:
            return text
        return self._pattern.sub(lambda m: self._lookup[m.group(0)], text)

    def add(self, surface: str, reading: str, kind: str = "noun") -> None:
        self.words.append(LexiconWord(surface=surface, reading=reading, kind=kind))
        self._build_pattern()

    def known_surface(self, surface: str) -> bool:
        return any(w.surface == surface for w in self.words)


def load(path: Path | None) -> Lexicon:
    """Load lexicon.yaml. Missing or empty file → empty lexicon."""
    if path is None or not path.exists():
        return Lexicon()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    words = [
        LexiconWord(surface=w["surface"], reading=w["reading"], kind=w.get("kind", "noun"))
        for w in (raw.get("words") or [])
        if w.get("surface") and w.get("reading")
    ]
    return Lexicon(words=words)


def save(lexicon: Lexicon, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"words": [
        {"surface": w.surface, "reading": w.reading, "kind": w.kind}
        for w in lexicon.words
    ]}
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path
