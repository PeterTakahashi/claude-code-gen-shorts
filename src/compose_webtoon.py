"""Render bubbles onto each chapter panel and stitch them into a single webtoon PNG.

For one chapter:
  - Reads scenes.json (panel structure + reuse_from) and bubbles.json (text + style)
  - Renders bubbles onto each panel image → bubbled/<scene_id>/<pid>_bubbled.png
  - Stacks vertically with per-panel gaps → output/<chapter>/webtoon.png
  - Writes panel_positions.json describing each panel's y_start/y_end in the
    composed image (used by scroll_video.py to align audio to scroll position).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from .bubble_renderer import render_bubbles_on_panel
from .composer import _resize_to_width, gap_from_distance_token
from .project import Chapter, ProjectContext, load
from .render_panels import resolve_reuse_from


def _panel_source_path(project: ProjectContext, chapter: Chapter, panel: dict) -> Path:
    reuse = panel.get("reuse_from")
    if reuse:
        return resolve_reuse_from(project, chapter, reuse)
    pid = panel["panel_id"]
    scene_id = "_".join(pid.split("_")[:2])
    return chapter.panels_dir / scene_id / f"{pid}_best.png"


def compose_chapter(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> Path:
    if not chapter.scenes_json.exists():
        raise FileNotFoundError(f"missing {chapter.scenes_json}")
    if not chapter.bubbles_json.exists():
        raise FileNotFoundError(f"missing {chapter.bubbles_json}")

    scenes_cfg = json.loads(chapter.scenes_json.read_text(encoding="utf-8"))
    bubbles_cfg = json.loads(chapter.bubbles_json.read_text(encoding="utf-8"))
    bubbles_by_panel = {p["panel_id"]: p.get("bubbles", []) for p in bubbles_cfg.get("panels", [])}

    # project.yaml is the canonical source. bubbles.json font_* only acts as a
    # fallback for legacy data — never as an override.
    font_path = project.bubble_font_path or bubbles_cfg.get("font_main") or ""
    font_index = int(project.bubble_font_index if project.bubble_font_index else bubbles_cfg.get("font_index", 0))
    font_scale = float(project.bubble_font_scale if project.bubble_font_scale else bubbles_cfg.get("font_scale", 1.0))

    chapter.bubbled_dir.mkdir(parents=True, exist_ok=True)
    panel_paths: list[Path] = []
    gaps: list[int] = []
    gap_table = project.panel_gap_px

    scenes = scenes_cfg["scenes"]
    for si, scene in enumerate(scenes):
        scene_id = scene["id"]
        scene_bubbled_dir = chapter.bubbled_dir / scene_id
        scene_bubbled_dir.mkdir(parents=True, exist_ok=True)
        panels = scene["panels"]

        for pi, panel in enumerate(panels):
            pid = panel["panel_id"]
            src = _panel_source_path(project, chapter, panel)
            if not src.exists():
                print(f"skip missing: {pid}  ({src})")
                continue

            bubbles = bubbles_by_panel.get(pid, [])
            if bubbles:
                dst = scene_bubbled_dir / f"{pid}_bubbled.png"
                if not dst.exists() or force:
                    render_bubbles_on_panel(src, bubbles, font_path, font_index, dst, font_scale=font_scale)
                use = dst
            else:
                use = src

            panel_paths.append(use)
            is_last_in_scene = pi == len(panels) - 1
            if is_last_in_scene:
                if si < len(scenes) - 1:
                    gaps.append(gap_from_distance_token(panel.get("distance_to_next_panel", "jump"), gap_table))
            else:
                gaps.append(gap_from_distance_token(panel.get("distance_to_next_panel", "breath"), gap_table))

    gaps = gaps[: len(panel_paths) - 1]
    out_img = chapter.webtoon_png
    out_img.parent.mkdir(parents=True, exist_ok=True)
    width = project.webtoon_width

    resized = [_resize_to_width(Image.open(p).convert("RGB"), width) for p in panel_paths]
    total_h = sum(im.height for im in resized) + sum(gaps)
    canvas = Image.new("RGB", (width, total_h), "white")
    positions: list[dict] = []
    y = 0
    for i, (im, panel_path) in enumerate(zip(resized, panel_paths)):
        positions.append({
            "index": i,
            "source_path": str(panel_path),
            "y_start": y,
            "y_end": y + im.height,
            "height": im.height,
        })
        canvas.paste(im, (0, y))
        y += im.height
        if i < len(gaps):
            y += gaps[i]
    canvas.save(out_img)

    panel_id_seq: list[str] = [p["panel_id"] for s in scenes for p in s["panels"]]
    for pos, pid in zip(positions, panel_id_seq):
        pos["panel_id"] = pid

    chapter.panel_positions_json.parent.mkdir(parents=True, exist_ok=True)
    chapter.panel_positions_json.write_text(
        json.dumps({
            "image": str(out_img),
            "width": width,
            "height": total_h,
            "panels": positions,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    w, h = canvas.size
    print(f"\n✅ wrote {out_img} ({w}x{h})  panels={len(panel_paths)}")
    print(f"   panel_positions.json written with {len(positions)} entries")
    return out_img


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.compose_webtoon <project_id> <chapter_id> [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    compose_chapter(project, chapter, force="--force" in sys.argv)


if __name__ == "__main__":
    main()
