"""Generate per-panel SFX wavs from a chapter's bubbles.json.

bubbles.json shape (additive — panels without `sfx[]` are skipped):
  panels[].sfx[] = [
    { "id": "sfx_01",
      "elevenlabs_prompt": "soft footsteps on wooden floorboards",
      "duration_s": 1.5,           # optional
      "start_offset_s": 0.0,       # used by audio mixer (M4), not by us
      "volume_db": -8,             # used by audio mixer (M4), not by us
      "prompt_influence": 0.4 }    # optional, default 0.3

Output: <chapter.audio_sfx_dir>/<panel_id>_<sfx_id>.mp3

Idempotent — skips a clip if the file already exists, unless force=True.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .elevenlabs import generate_sound_effect
from .project import Chapter, ProjectContext, load


def synthesize_chapter_sfx(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> int:
    if not chapter.bubbles_json.exists():
        raise FileNotFoundError(f"missing {chapter.bubbles_json}")
    cfg = json.loads(chapter.bubbles_json.read_text(encoding="utf-8"))

    chapter.audio_sfx_dir.mkdir(parents=True, exist_ok=True)
    n_done = 0
    n_skipped = 0
    n_total = sum(len(p.get("sfx") or []) for p in cfg.get("panels", []))
    if n_total == 0:
        print("  (no sfx[] entries in bubbles.json — skipping)")
        return 0

    for panel in cfg.get("panels", []):
        pid = panel["panel_id"]
        for sfx in panel.get("sfx") or []:
            sid = sfx.get("id") or f"sfx_{len([s for s in panel.get('sfx') or []]):02d}"
            out = chapter.audio_sfx_dir / f"{pid}_{sid}.mp3"
            if out.exists() and not force:
                n_skipped += 1
                continue

            prompt = sfx.get("elevenlabs_prompt") or sfx.get("prompt")
            if not prompt:
                print(f"  ⚠ skip {pid} / {sid}: missing elevenlabs_prompt")
                continue
            duration = sfx.get("duration_s")
            influence = float(sfx.get("prompt_influence", 0.3))

            print(f"  [{n_done + n_skipped + 1}/{n_total}] {pid}/{sid}  dur={duration}s  prompt={prompt[:60]!r}")
            try:
                generate_sound_effect(prompt, out, duration_seconds=duration, prompt_influence=influence)
                n_done += 1
            except Exception as e:
                print(f"    ⚠ failed: {e}")

    print(f"\n  ✅ sfx: generated={n_done}, skipped={n_skipped}, total={n_total}")
    return n_done


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.synth_sfx <project_id> <chapter_id> [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    synthesize_chapter_sfx(project, chapter, force="--force" in sys.argv)


if __name__ == "__main__":
    main()
