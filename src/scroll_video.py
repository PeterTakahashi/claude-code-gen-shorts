"""Build a "hold-then-scroll" narrated webtoon video.

UX pattern (per user request):
  - While a panel's narration plays: the panel is HELD still (no scrolling),
    centered inside a 1080×1920 page frame.
  - When the narration ends: a short vertical scroll transitions to the next
    panel's page frame.
  - Repeat for every panel.

Implementation:
  1. Scale the webtoon to 1080px wide.
  2. For each panel, render a 1080×1920 "page frame" with the panel image
     vertically centered against a neutral background.
  3. Hold clip: static page frame + narration audio (duration = audio length).
  4. Transition clip: stack the current and next page frames into a 1080×3840
     image, then ffmpeg crops a 1920-tall window whose y scrolls from 0 to 1920
     over a short duration (default 1.5s), silent.
  5. Concat all clips.

Outputs:
  - output/webtoon_first_memoir_scroll.mp4
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image

from .project import Chapter, ProjectContext, load


CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30
TRANSITION_S = 0.5
PAGE_BG = (20, 20, 20)  # near-black so page-to-page scroll feels cohesive


def probe_duration_seconds(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(args[:6])}…\n{r.stderr[-2000:]}")


def build_page_image(
    scaled_webtoon: Image.Image,
    panel_y_top: int,
    panel_y_bottom: int,
    out_path: Path,
) -> Path:
    """Render a 1080×1920 page frame: the panel centered, padding around it."""
    panel_h = panel_y_bottom - panel_y_top
    cropped = scaled_webtoon.crop((0, panel_y_top, CANVAS_W, panel_y_bottom))
    page = Image.new("RGB", (CANVAS_W, CANVAS_H), PAGE_BG)
    if panel_h <= CANVAS_H:
        # Center vertically.
        y_off = (CANVAS_H - panel_h) // 2
        page.paste(cropped, (0, y_off))
    else:
        # Taller than the frame — show the top portion (rare with our panel sizes).
        page.paste(cropped.crop((0, 0, CANVAS_W, CANVAS_H)), (0, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(out_path)
    return out_path


def render_hold_clip(page_path: Path, audio_path: Path, out_path: Path) -> Path:
    dur = probe_duration_seconds(audio_path)
    _ffmpeg([
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{dur:.4f}", "-i", str(page_path),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-t", f"{dur:.4f}",
        str(out_path),
    ])
    return out_path


def render_transition_clip(
    page_a_path: Path,
    page_b_path: Path,
    out_path: Path,
    duration_s: float = TRANSITION_S,
) -> Path:
    """Create a 1.5s scroll from page_a to page_b (silent)."""
    # Stack vertically into a 1080×3840 image.
    a = Image.open(page_a_path).convert("RGB")
    b = Image.open(page_b_path).convert("RGB")
    stacked_h = CANVAS_H * 2
    stacked = Image.new("RGB", (CANVAS_W, stacked_h), PAGE_BG)
    stacked.paste(a, (0, 0))
    stacked.paste(b, (0, CANVAS_H))
    stacked_path = out_path.with_suffix(".stack.png")
    stacked.save(stacked_path)

    y_expr = f"{CANVAS_H}*t/{duration_s:.4f}"
    # Silent audio track of matching duration (keeps A/V streams uniform for concat).
    _ffmpeg([
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{duration_s:.4f}", "-i", str(stacked_path),
        "-f", "lavfi", "-t", f"{duration_s:.4f}", "-i",
        "anullsrc=channel_layout=mono:sample_rate=44100",
        "-filter_complex",
        f"[0:v]crop=w={CANVAS_W}:h={CANVAS_H}:x=0:y='{y_expr}',fps={FPS},format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{duration_s:.4f}",
        str(out_path),
    ])
    stacked_path.unlink(missing_ok=True)
    return out_path


def rescale_webtoon(src: Path, dst: Path, target_w: int) -> Image.Image:
    img = Image.open(src).convert("RGB")
    W_src, H_src = img.size
    scale = target_w / W_src
    H_out = int(round(H_src * scale))
    resized = img.resize((target_w, H_out), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    resized.save(dst)
    return resized


def build_scroll_video(
    project: ProjectContext,
    chapter: Chapter,
    *,
    force: bool = False,
) -> Path:
    positions_path = chapter.panel_positions_json
    source_webtoon = chapter.webtoon_png
    out_mp4 = chapter.webtoon_scroll_mp4

    positions = json.loads(positions_path.read_text(encoding="utf-8"))
    panels = positions["panels"]
    native_w = positions["width"]

    pages_dir = chapter.pages_dir
    clips_dir = chapter.video_segs_dir
    audio_dir = chapter.audio_dir
    pages_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Scale the webtoon once.
    scaled_png = chapter.webtoon_for_video_png
    scale = CANVAS_W / native_w
    if not scaled_png.exists() or force:
        rescale_webtoon(source_webtoon, scaled_png, CANVAS_W)
    scaled_img = Image.open(scaled_png).convert("RGB")

    # Build per-panel page images.
    page_paths: list[Path] = []
    for p in panels:
        pid = p["panel_id"]
        y_top = int(round(p["y_start"] * scale))
        y_bot = int(round(p["y_end"] * scale))
        page_path = pages_dir / f"{pid}.png"
        if not page_path.exists() or force:
            build_page_image(scaled_img, y_top, y_bot, page_path)
        page_paths.append(page_path)

    # Render hold + transition clips.
    clip_paths: list[Path] = []
    total_s = 0.0
    for i, p in enumerate(panels):
        pid = p["panel_id"]
        audio = audio_dir / f"{pid}.mp3"
        if not audio.exists():
            print(f"skip missing audio: {pid}")
            continue

        hold_path = clips_dir / f"{pid}_hold.mp4"
        if not hold_path.exists() or force:
            print(f"[hold {i+1}/{len(panels)}] {pid}  dur={probe_duration_seconds(audio):.2f}s")
            render_hold_clip(page_paths[i], audio, hold_path)
        clip_paths.append(hold_path)
        total_s += probe_duration_seconds(hold_path)

        if i < len(panels) - 1:
            trans_path = clips_dir / f"{pid}_to_next.mp4"
            if not trans_path.exists() or force:
                print(f"[trans {i+1}] {pid} → {panels[i+1]['panel_id']}")
                render_transition_clip(page_paths[i], page_paths[i + 1], trans_path)
            clip_paths.append(trans_path)
            total_s += TRANSITION_S

    # Concat.
    concat_list = clips_dir / "all.concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clip_paths),
        encoding="utf-8",
    )
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        str(out_mp4),
    ])
    print(f"\n✅ {out_mp4}  (~{total_s:.1f}s, {len(clip_paths)} clips)")
    return out_mp4


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m src.scroll_video <project_id> <chapter_id> [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    build_scroll_video(project, chapter, force="--force" in sys.argv)
