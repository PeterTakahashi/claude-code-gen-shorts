"""End-to-end chapter builder for biography webtoons.

Given a chapter that already has `novel.txt`, `scenes.json`, and `bubbles.json`,
run the full pipeline to produce `output/<chapter>/master.mp4` + `thumbnail.png`:

  1. arabize_bubbles   — convert kanji numbers to Arabic numerals
  2. render_panels     — Gemini batch generation of panel PNGs (~25-60 min)
  3. narrate           — Aivis TTS per bubble
  4. audio_mixer       — voice + SFX → chapter_master.wav
  5. video_assembler   — 1920x1080 still cuts + baked subtitles → master.mp4
  6. thumbnail_gen     — 1280x720 YouTube thumbnail

Each stage is idempotent: if its output exists, the stage is skipped unless
`--force` is passed (which forwards to all stages that accept it).

Usage:
  uv run python -m src.build_chapter <project_id> <chapter_id>
  uv run python -m src.build_chapter <project_id> <chapter_id> --force
  uv run python -m src.build_chapter <project_id> <chapter_id> --skip-render
  uv run python -m src.build_chapter <project_id> <chapter_id> --series "シリーズ名"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from .project import load


def _run(label: str, cmd: list[str], *, optional: bool = False) -> bool:
    print(f"\n===== {label} =====")
    print(f"  $ {' '.join(cmd)}")
    started = time.time()
    r = subprocess.run(cmd)
    elapsed = time.time() - started
    if r.returncode != 0:
        if optional:
            print(f"  ⚠️ {label} returned {r.returncode} ({elapsed:.1f}s) — continuing")
            return False
        print(f"  ❌ {label} failed (exit {r.returncode}, {elapsed:.1f}s)", file=sys.stderr)
        sys.exit(r.returncode)
    print(f"  ✓ {label} done ({elapsed:.1f}s)")
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("chapter_id")
    p.add_argument("--force", action="store_true", help="Force regenerate every stage")
    p.add_argument("--skip-render", action="store_true", help="Skip panel image generation (assume done)")
    p.add_argument("--skip-thumbnail", action="store_true")
    p.add_argument("--series", default=None, help="Series label for thumbnail top-right ribbon")
    p.add_argument("--poll-interval", type=float, default=30.0, help="Gemini batch poll seconds")
    args = p.parse_args()

    project = load(args.project_id)
    chapter = project.chapter(args.chapter_id)

    # Pre-flight: required input files
    for must in (chapter.novel_txt, chapter.scenes_json, chapter.bubbles_json):
        if not must.exists():
            print(f"ERROR: missing required input: {must}", file=sys.stderr)
            return 1

    py = [sys.executable, "-m"]
    force_flag = ["--force"] if args.force else []
    pid, cid = args.project_id, args.chapter_id

    _run("arabize_bubbles", py + ["src.arabize_bubbles", pid, cid])

    if not args.skip_render:
        _run(
            "render_panels (Gemini batch — this can take 25–60 min)",
            py + ["src.render_panels", pid, cid, "--batch", f"--poll-interval={args.poll_interval}"] + force_flag,
        )

    _run("narrate (Aivis TTS)", py + ["src.narrate", pid, cid] + force_flag)
    _run("audio_mixer (voice + sfx)", py + ["src.audio_mixer", pid, cid] + force_flag)
    _run("video_assembler (master.mp4)", py + ["src.video_assembler", pid, cid] + force_flag)

    if not args.skip_thumbnail:
        cmd = py + ["src.thumbnail_gen", pid, cid]
        if args.series:
            cmd += ["--series", args.series]
        _run("thumbnail_gen (1280x720)", cmd, optional=True)

    print(f"\n✅ {pid}/{cid} ready:")
    print(f"   video     : {chapter.master_mp4}")
    print(f"   subtitles : {chapter.subtitles_srt}")
    thumb = chapter.output_dir / "thumbnail.png"
    if thumb.exists():
        print(f"   thumbnail : {thumb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
