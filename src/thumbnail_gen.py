"""Generate 1280x720 YouTube thumbnails from a chapter panel image.

Layout:
  - Background: source panel image, center-cropped to 1280x720 with subtle vignette
  - Top-left: episode number ribbon (e.g. "第3話")
  - Bottom band: solid dark gradient with title text in NotoSansJP white

Usage:
  uv run python -m src.thumbnail_gen <project_id> <chapter_id> [--source <panel.png>] [--out <path>]

If --source is omitted, defaults to scene_05_p02_best.png (typical mid-chapter beat).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .project import load

ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "assets" / "fonts" / "NotoSansJP-Regular.otf"
FONT_BOLD_PATH = ROOT / "assets" / "fonts" / "NotoSansJP-Bold.otf"

W, H = 1280, 720


def _fit_center_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    sw, sh = img.size
    target_ratio = w / h
    src_ratio = sw / sh
    if src_ratio > target_ratio:
        new_w = int(sh * target_ratio)
        x0 = (sw - new_w) // 2
        img = img.crop((x0, 0, x0 + new_w, sh))
    else:
        new_h = int(sw / target_ratio)
        y0 = (sh - new_h) // 2
        img = img.crop((0, y0, sw, y0 + new_h))
    return img.resize((w, h), Image.LANCZOS)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    fp = FONT_BOLD_PATH if bold and FONT_BOLD_PATH.exists() else FONT_PATH
    return ImageFont.truetype(str(fp), size)


def _wrap_japanese_for_width(text: str, font: ImageFont.FreeTypeFont, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] > max_w and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def make_thumbnail(
    source_panel: Path,
    episode_label: str,
    title: str,
    out_path: Path,
    series_label: str | None = None,
) -> Path:
    img = Image.open(source_panel).convert("RGB")
    canvas = _fit_center_crop(img, W, H).convert("RGBA")

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Bottom gradient band
    band_h = 280
    for i in range(band_h):
        alpha = int(220 * (i / band_h) ** 1.2)
        draw.rectangle([(0, H - band_h + i), (W, H - band_h + i + 1)], fill=(0, 0, 0, alpha))

    # Top-left ribbon: episode_label
    ep_font = _load_font(80, bold=True)
    ep_pad = 18
    ep_bbox = draw.textbbox((0, 0), episode_label, font=ep_font)
    ep_w = ep_bbox[2] - ep_bbox[0]
    ep_h = ep_bbox[3] - ep_bbox[1]
    ribbon_w = ep_w + ep_pad * 2
    ribbon_h = ep_h + ep_pad * 2
    draw.rectangle([(0, 30), (ribbon_w, 30 + ribbon_h)], fill=(220, 38, 38, 240))
    draw.text((ep_pad, 30 + ep_pad - 8), episode_label, font=ep_font, fill=(255, 255, 255, 255))

    # Top-right series label
    if series_label:
        sl_font = _load_font(38)
        sl_bbox = draw.textbbox((0, 0), series_label, font=sl_font)
        sl_w = sl_bbox[2] - sl_bbox[0]
        sl_h = sl_bbox[3] - sl_bbox[1]
        sl_pad = 14
        sl_x = W - sl_w - sl_pad * 2 - 20
        sl_y = 30
        draw.rectangle([(sl_x, sl_y), (sl_x + sl_w + sl_pad * 2, sl_y + sl_h + sl_pad * 2)], fill=(0, 0, 0, 200))
        draw.text((sl_x + sl_pad, sl_y + sl_pad - 6), series_label, font=sl_font, fill=(255, 255, 255, 255))

    # Title in bottom band
    title_font = _load_font(72, bold=True)
    margin = 40
    lines = _wrap_japanese_for_width(title, title_font, W - margin * 2, draw)
    line_gap = 14
    line_h = title_font.size + line_gap
    total_h = line_h * len(lines)
    y0 = H - 60 - total_h
    for i, ln in enumerate(lines):
        bbox = draw.textbbox((0, 0), ln, font=title_font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        y = y0 + i * line_h
        # Stroke
        for dx in (-3, -2, 0, 2, 3):
            for dy in (-3, -2, 0, 2, 3):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), ln, font=title_font, fill=(0, 0, 0, 255))
        draw.text((x, y), ln, font=title_font, fill=(255, 255, 255, 255))

    composed = Image.alpha_composite(canvas, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(out_path, format="PNG", optimize=True)
    print(f"  wrote {out_path}  ({W}x{H})")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("chapter_id")
    p.add_argument("--source", type=Path, default=None,
                   help="Source panel image; defaults to scene_05_p02_best.png in chapter panels dir")
    p.add_argument("--out", type=Path, default=None,
                   help="Output path; defaults to output/<chapter>/thumbnail.png")
    p.add_argument("--episode", default=None, help="Episode label (e.g. '第3話'). Auto-derived if omitted.")
    p.add_argument("--title", default=None, help="Title text. Defaults to chapter.title from project.yaml.")
    p.add_argument("--series", default=None, help="Series label (top-right).")
    args = p.parse_args()

    project = load(args.project_id)
    chapter = project.chapter(args.chapter_id)

    if args.source:
        source = args.source
    else:
        # default to scene_05_p02 if exists, else first available
        candidates = [
            chapter.panels_dir / "scene_05" / "scene_05_p02_best.png",
            chapter.panels_dir / "scene_07" / "scene_07_p01_best.png",
            chapter.panels_dir / "scene_03" / "scene_03_p01_best.png",
            chapter.panels_dir / "scene_01" / "scene_01_p01_best.png",
        ]
        source = next((c for c in candidates if c.exists()), None)
        if not source:
            raise FileNotFoundError(f"no panel image found in {chapter.panels_dir}")

    out = args.out or (chapter.output_dir / "thumbnail.png")

    # Auto-derive title from project.yaml chapter title.
    full_title = args.title or chapter.title  # e.g. "第一話 雷鳴と追放"
    if args.episode:
        episode_label = args.episode
    else:
        # Extract leading "第X話" or fall back to chapter id.
        episode_label = full_title.split(" ")[0] if "話" in full_title else chapter.id

    body_title = full_title.split(" ", 1)[1] if " " in full_title else full_title

    make_thumbnail(source, episode_label, body_title, out, series_label=args.series)


if __name__ == "__main__":
    main()
