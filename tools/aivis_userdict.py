#!/usr/bin/env python3
"""Register reading overrides into the Aivis (VOICEVOX-compatible) user dictionary.

Aivis exposes /user_dict_word (surface -> pronunciation in katakana + accent).
Registering names/terms here makes ALL synthesis read them correctly while the
narration text stays as normal KANJI (no kana-hacking needed). The engine
persists the dictionary across restarts.

Run:  .venv/bin/python tools/aivis_userdict.py
"""
import sys
import requests

ENDPOINT = "http://127.0.0.1:10101"

# (surface, katakana reading, accent_type). accent_type = mora index of the
# downstep (0 = heiban / flat, usually safe for names). Reading correctness
# matters most; tweak accent if the pitch sounds off.
WORDS = [
    ("舛岡富士雄", "マスオカフジオ", 0),
    ("王貞治", "オウサダハル", 0),
    ("羽生結弦", "ハニュウユヅル", 0),
    ("羽生", "ハニュウ", 0),          # force はにゅう (not はぶ) for the skater
    ("国中", "クニジュウ", 0),
    ("氷上", "ヒョウジョウ", 0),
    ("柳井正", "ヤナイタダシ", 0),
    ("柳井", "ヤナイ", 0),
    ("孫正義", "ソンマサヨシ", 0),
]


def existing_surfaces() -> set[str]:
    try:
        r = requests.get(f"{ENDPOINT}/user_dict", timeout=10)
        return {w.get("surface") for w in r.json().values()}
    except Exception:
        return set()


def main() -> int:
    have = existing_surfaces()
    for surface, yomi, accent in WORDS:
        if surface in have:
            print(f"  = already registered: {surface} -> {yomi}")
            continue
        r = requests.post(
            f"{ENDPOINT}/user_dict_word",
            params={"surface": surface, "pronunciation": yomi,
                    "accent_type": accent, "word_type": "PROPER_NOUN", "priority": 8},
            timeout=15,
        )
        if r.status_code == 200:
            print(f"  + registered: {surface} -> {yomi}  (uuid={r.text.strip()[:40]})")
        else:
            print(f"  ! FAILED {surface}: [{r.status_code}] {r.text[:160]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
