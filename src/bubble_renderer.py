"""Render monologue/speech boxes onto panel images using Pillow.

Supports:
- narration_box:  white text on semi-transparent black bar (manga caption style)
- monologue_box:  rounded rectangle with white fill + black border, black text
- speech:         (not yet used)  oval balloon with black border
- thought:        (not yet used)  cloud-shaped balloon
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _load_font(path: str, size_px: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size_px, index=index)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word/char wrap for Japanese text at max pixel width."""
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        w = draw.textlength(trial, font=font)
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = trial
        # honour explicit newlines too
        if ch == "\n":
            lines.append(current.rstrip("\n"))
            current = ""
    if current:
        lines.append(current)
    return lines


# Punctuation that needs rotation/translation when drawn in vertical (tate-gaki) mode.
# For simplicity, characters not in this table are drawn as-is, top-down.
_TATE_ROTATE_CHARS = set("ー−―〜～…‥（）「」『』〔〕【】｛｝<>《》≪≫")
_TATE_SHIFT_CHARS = {
    "、": (0.5, -0.3),   # shift right and up inside em box
    "。": (0.5, -0.3),
    "．": (0.5, -0.3),
    "，": (0.5, -0.3),
}


def _wrap_vertical_columns(
    text: str,
    chars_per_column: int,
) -> list[str]:
    """Split text into columns (top→bottom) that will be laid out right→left.
    Explicit \n forces a new column."""
    cols: list[str] = []
    cur = ""
    for ch in text:
        if ch == "\n":
            if cur:
                cols.append(cur)
                cur = ""
            continue
        cur += ch
        if len(cur) >= chars_per_column:
            cols.append(cur)
            cur = ""
    if cur:
        cols.append(cur)
    return cols


def _draw_vertical_char(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    ch: str,
    x: int,
    y: int,
    em: int,
    font: ImageFont.FreeTypeFont,
    fill,
) -> None:
    """Draw a single char within its em box at (x, y)."""
    if ch in _TATE_ROTATE_CHARS:
        # Render onto a transparent tile, rotate 90° CW, paste.
        tile = Image.new("RGBA", (em, em), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        # Center the char in tile, then rotate.
        tw = td.textlength(ch, font=font)
        th = em
        td.text(((em - tw) / 2, (em - th) / 2), ch, font=font, fill=fill)
        tile = tile.rotate(-90, resample=Image.BICUBIC)
        img.paste(tile, (x, y), tile)
        return
    if ch in _TATE_SHIFT_CHARS:
        dx, dy = _TATE_SHIFT_CHARS[ch]
        draw.text((x + int(em * dx), y + int(em * dy)), ch, font=font, fill=fill)
        return
    # default: center horizontally inside em box
    tw = draw.textlength(ch, font=font)
    draw.text((x + (em - tw) // 2, y), ch, font=font, fill=fill)


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill,
    outline,
    width: int,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def render_bubbles_on_panel(
    panel_image_path: Path,
    bubbles: list[dict[str, Any]],
    font_path: str,
    font_index: int = 0,
    out_path: Path | None = None,
    font_scale: float = 1.0,
) -> Path:
    img = Image.open(panel_image_path).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    for b in bubbles:
        btype = b["type"]
        text = b["text"]
        pos = b["position"]
        x = int(W * pos["x_pct"] / 100)
        y = int(H * pos["y_pct"] / 100)
        box_w = int(W * b["width_pct"] / 100)

        # rough mapping: pt → px at 96 dpi assumption (*1.33) — but our images are high-res; use a scale based on image width.
        pt = b.get("font_size_pt", 18) * font_scale
        # Scale font size by image width so webtoon renders evenly regardless of native panel resolution.
        size_px = max(12, int(pt * W / 800))
        font = _load_font(font_path, size_px, index=font_index)

        pad = max(8, size_px // 2)
        inner_w = box_w - 2 * pad

        vertical = bool(b.get("vertical_text", False))

        if vertical:
            em = size_px
            # Max available height for the column text (use panel bottom minus y).
            hpct_cap = b.get("height_pct", 90)
            max_box_h = int(H * hpct_cap / 100)
            max_chars_per_column = max(1, (max_box_h - 2 * pad) // em)
            columns = _wrap_vertical_columns(text, max_chars_per_column)
            # Actual box height = (longest column length) * em + padding.
            longest = max((len(c) for c in columns), default=1)
            box_h = longest * em + 2 * pad
            # Width fits the number of columns.
            box_w = len(columns) * em + 2 * pad
            inner_w = box_w - 2 * pad
        else:
            lines = _wrap_text(draw, text, font, inner_w)
            line_h = int(size_px * 1.35)
            text_h = line_h * len(lines)
            box_h = text_h + 2 * pad

        # Draw box
        x0, y0 = x, y
        x1, y1 = x + box_w, y + box_h

        if btype == "narration_box":
            # semi-transparent black bar, white text
            draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 200))
            text_fill = (255, 255, 255)
        elif btype in ("monologue_box", "thought"):
            # white rounded rect with black outline, black text
            _draw_rounded_rect(
                draw,
                (x0, y0, x1, y1),
                radius=max(10, size_px // 2),
                fill=(255, 255, 255, 245),
                outline=(0, 0, 0, 255),
                width=max(2, size_px // 10),
            )
            text_fill = (0, 0, 0)
        elif btype == "speech":
            # ellipse balloon, white fill, black border, black text
            draw.ellipse((x0, y0, x1, y1), fill=(255, 255, 255, 245), outline=(0, 0, 0), width=max(2, size_px // 10))
            text_fill = (0, 0, 0)
        else:
            raise ValueError(f"unknown bubble type: {btype}")

        # Draw text
        if vertical:
            em = size_px
            # Right-to-left columns: first column is rightmost.
            col_x = x1 - pad - em
            for col in columns:
                ty = y0 + pad
                for ch in col:
                    _draw_vertical_char(img, draw, ch, col_x, ty, em, font, text_fill)
                    ty += em
                col_x -= em
        else:
            ty = y0 + pad
            for ln in lines:
                tw = draw.textlength(ln, font=font)
                tx = x0 + (box_w - tw) // 2
                draw.text((tx, ty), ln, font=font, fill=text_fill)
                ty += line_h

    if out_path is None:
        out_path = panel_image_path.with_name(panel_image_path.stem + "_bubbled.png")
    img.save(out_path)
    return out_path


def render_beat(
    bubbles_json_path: Path,
    panels_dir: Path,
    out_dir: Path,
) -> list[Path]:
    cfg = json.loads(bubbles_json_path.read_text(encoding="utf-8"))
    font_path = cfg["font_main"]
    font_index = int(cfg.get("font_index", 0))
    font_scale = float(cfg.get("font_scale", 1.0))

    out_paths: list[Path] = []
    for panel_cfg in cfg["panels"]:
        pid = panel_cfg["panel_id"]
        src = panels_dir / f"{pid}_best.png"
        dst = out_dir / f"{pid}_bubbled.png"
        render_bubbles_on_panel(
            src, panel_cfg["bubbles"], font_path, font_index, dst, font_scale=font_scale
        )
        out_paths.append(dst)
    return out_paths
