#!/usr/bin/env python3
"""Transcribe a short's narration audio with Whisper to catch TTS misreadings.

Runs in the flux2-mlx venv (has mlx-whisper). For each (project, short_id), it
transcribes the narration mp3 and prints the recognized text so misread kanji /
names / numbers can be caught before upload.

Usage (from repo root, flux2-mlx python):
  ~/flux2-mlx/bin/python tools/verify_tts.py <project> <short_id> [<project> <short_id> ...]
"""
import sys
from pathlib import Path
import mlx_whisper

MODEL = "mlx-community/whisper-large-v3-turbo"
ROOT = Path("/Users/apple/dev/claude-code/webtoon-gen")


def narration_path(project: str, sid: str) -> Path | None:
    base = ROOT / "projects" / project / "output" / "shorts" / sid / "ja"
    for name in ("narration.mp3", "narration_with_sfx.mp3"):
        p = base / name
        if p.exists():
            return p
    return None


def main() -> int:
    args = sys.argv[1:]
    pairs = list(zip(args[0::2], args[1::2]))
    for project, sid in pairs:
        p = narration_path(project, sid)
        if not p:
            print(f"\n[{project}/{sid}] NO narration audio found")
            continue
        r = mlx_whisper.transcribe(str(p), path_or_hf_repo=MODEL, language="ja")
        text = r.get("text", "").strip()
        print(f"\n=== {project}/{sid} ===")
        print(f"WHISPER: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
