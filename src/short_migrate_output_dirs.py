"""Move existing JA output files from output/shorts/<sid>/* to output/shorts/<sid>/ja/*.

The path schema changed: language always lives in its own subfolder.
This script moves the pre-existing JA files (short.mp4, thumbnail.jpg, thumbnail.png,
narration.mp3) under the new `ja/` subdir.

Idempotent: skips files already migrated, leaves panels-related shared files alone.

Usage:
  uv run python -m src.short_migrate_output_dirs [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files in output/shorts/<sid>/ that are JA-specific and should move under ja/.
JA_FILES = {"short.mp4", "thumbnail.jpg", "thumbnail.png", "narration.mp3", "subtitles.srt"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    moved = 0
    skipped = 0
    for short_dir in sorted((ROOT / "projects").glob("*/output/shorts/*")):
        if not short_dir.is_dir():
            continue
        ja_dir = short_dir / "ja"
        for f in JA_FILES:
            src = short_dir / f
            if not src.exists() or not src.is_file():
                continue
            dst = ja_dir / f
            if dst.exists():
                skipped += 1
                continue
            ja_dir.mkdir(exist_ok=True)
            print(f"  mv {src.relative_to(ROOT)}  →  {dst.relative_to(ROOT)}")
            if not args.dry_run:
                shutil.move(str(src), str(dst))
            moved += 1
    print(f"\nmoved {moved} files, skipped {skipped} already migrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
