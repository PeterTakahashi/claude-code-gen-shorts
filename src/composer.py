"""Stack panel images vertically into a webtoon-format image."""
from __future__ import annotations

from pathlib import Path

from PIL import Image


DEFAULT_PANEL_GAP_PX = {"tight": 20, "breath": 80, "jump": 200}


def _resize_to_width(img: Image.Image, width: int) -> Image.Image:
    if img.width == width:
        return img
    ratio = width / img.width
    new_h = int(img.height * ratio)
    return img.resize((width, new_h), Image.LANCZOS)


def compose_webtoon(
    panel_paths: list[Path],
    gaps: list[int],
    out_path: Path,
    width: int = 800,
    background: str = "white",
) -> Path:
    """Stack panels vertically with gaps between them."""
    if len(gaps) != len(panel_paths) - 1 and len(gaps) != len(panel_paths):
        raise ValueError("gaps must have len == panels-1 or == panels")
    inter_gaps = gaps[: len(panel_paths) - 1]

    resized = [_resize_to_width(Image.open(p).convert("RGB"), width) for p in panel_paths]
    total_h = sum(im.height for im in resized) + sum(inter_gaps)
    canvas = Image.new("RGB", (width, total_h), background)

    y = 0
    for i, im in enumerate(resized):
        canvas.paste(im, (0, y))
        y += im.height
        if i < len(inter_gaps):
            y += inter_gaps[i]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


def gap_from_distance_token(token: str, gap_px: dict[str, int] | None = None) -> int:
    table = gap_px or DEFAULT_PANEL_GAP_PX
    return table.get(token, table["breath"])
