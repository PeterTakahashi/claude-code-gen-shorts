"""Build a HORIZONTAL 16:9 long-form narrated video from a per-video YAML.

Companion to short_gen.py (which is vertical 9:16). Reuses the same YAML schema
(`panels` + `ja.narration`) and the short_gen TTS / timeline / ffmpeg helpers,
but composes a 1920×1080 landscape frame with lower-third subtitles instead of
the vertical hook-caption layout.

Differences vs short_gen:
  - Canvas 1920×1080 (landscape)
  - Panels generated as 16:9 landscape, cover-fit to fill the frame
  - Narration shown as a lower-third subtitle band (no persistent top hook)
  - Optional per-scene label (e.g. a date) top-left
  - Designed for 2-6 min explainer / story videos

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.longform_gen <project_id> <video_id>
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.longform_gen <project_id> <video_id> --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFilter

from .image_generator import generate_image
from .project import load
from . import short_gen as sg  # reuse helpers (TTS, timeline, fonts, ffmpeg)

ROOT = sg.ROOT
LW, LH = 1920, 1080
FPS = 30

LANDSCAPE_PREFIX = (
    "Generate a HORIZONTAL 16:9 landscape (1792x1024) cinematic image. "
    "Style: full-color modern anime / webtoon style, soft cel shading, expressive "
    "line art, cinematic lighting, serious documentary-drama tone. "
    "Compose for a wide 16:9 frame, subject and key action clearly placed, leaving the "
    "lower fifth of the frame relatively uncluttered for a subtitle band. "
    "Any in-image text (signs, screens, labels, captions) must be in JAPANESE, "
    "except real brand/product names which stay in English (Bybit, USDT, Coincheck). "
    "Scene: "
)


def _fit_landscape(src_path: Path, out_path: Path, force: bool = False) -> Path:
    """Cover-fit any source image to 1920×1080, with a subtle blurred letterbox
    fallback if the source is far from 16:9 (keeps the whole subject visible)."""
    if out_path.exists() and not force:
        return out_path
    img = Image.open(src_path).convert("RGB")
    sw, sh = img.size
    src_ratio = sw / sh
    target = LW / LH

    if abs(src_ratio - target) < 0.12:
        # close enough to 16:9 → cover-fit (minimal crop)
        scale = max(LW / sw, LH / sh)
        nw, nh = int(round(sw * scale)), int(round(sh * scale))
        scaled = img.resize((nw, nh), Image.LANCZOS)
        x0, y0 = (nw - LW) // 2, (nh - LH) // 2
        out = scaled.crop((x0, y0, x0 + LW, y0 + LH))
    else:
        # squarish source → contain on a blurred bokeh background (no crop of subject)
        scale = max(LW / sw, LH / sh)
        bw, bh = int(round(sw * scale)), int(round(sh * scale))
        bg = img.resize((bw, bh), Image.LANCZOS).crop(
            ((bw - LW) // 2, (bh - LH) // 2, (bw - LW) // 2 + LW, (bh - LH) // 2 + LH)
        ).filter(ImageFilter.GaussianBlur(radius=32))
        bg = Image.blend(bg, Image.new("RGB", (LW, LH), (0, 0, 0)), 0.35)
        fh = LH
        fw = int(round(sw * (LH / sh)))
        fg = img.resize((fw, fh), Image.LANCZOS)
        out = bg.copy()
        out.paste(fg, ((LW - fw) // 2, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path, format="PNG", optimize=True)
    return out_path


def _resolve_landscape_panel(project_id, key, prompt, work_dir, *, force=False, image_style="anime") -> Path:
    name = f"land_{key}" if isinstance(key, str) else f"land_{key:02d}"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    cache = work_dir / "panels" / f"{safe}.png"
    fitted = work_dir / "panels" / f"{safe}_fit.png"
    if fitted.exists() and not force:
        return fitted
    expanded = prompt
    for cid, desc in sg._char_descriptions(project_id).items():
        expanded = expanded.replace("{" + cid + "}", f"({desc})")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or force:
        print(f"    generating landscape panel {key} via Gemini …")
        generate_image(LANDSCAPE_PREFIX + expanded.strip(), cache)
    return _fit_landscape(cache, fitted, force=force)


def _compose_landscape_frame(base_panel: Path, out_path: Path, *, subtitle: str | None,
                             scene_label: str | None) -> Path:
    """1920×1080 frame: image fills, optional top-left scene label, lower-third subtitle."""
    img = Image.open(base_panel).convert("RGBA")
    if img.size != (LW, LH):
        img = img.resize((LW, LH), Image.LANCZOS)
    overlay = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # optional scene/date label, top-left
    if scene_label:
        lab_font = sg._load_font(46, bold=True)
        pad = 18
        bb = draw.textbbox((0, 0), scene_label, font=lab_font)
        lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        draw.rectangle([(40, 40), (40 + lw + pad * 2, 40 + lh + pad * 2)], fill=(0, 0, 0, 170))
        sg._stroke_text(draw, (40 + pad, 40 + pad), scene_label, lab_font, (255, 230, 120, 255), stroke_w=3)

    # lower-third subtitle band
    if subtitle:
        cap_font = sg._load_font(56, bold=True)
        margin = 120
        lines = sg._wrap_jp(draw, subtitle, cap_font, LW - margin * 2)
        line_h = int(56 * 1.34)
        total = line_h * len(lines)
        band_top = LH - 80 - total
        draw.rectangle([(0, band_top - 28), (LW, band_top + total + 28)], fill=(0, 0, 0, 175))
        y = band_top
        for ln in lines:
            bb = draw.textbbox((0, 0), ln, font=cap_font)
            x = (LW - (bb[2] - bb[0])) // 2
            sg._stroke_text(draw, (x, y), ln, cap_font, (255, 255, 255, 255), stroke_w=3)
            y += line_h

    composed = Image.alpha_composite(img, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(out_path, format="PNG", optimize=True)
    return out_path


def build_longform(project_id: str, video_id: str, *, force: bool = False,
                   language: str = "ja", speaker: str | None = None) -> Path:
    project = load(project_id)
    cfg_path = ROOT / "projects" / project_id / "longform" / f"{video_id}.yaml"
    if not cfg_path.exists():  # fall back to shorts/ dir (same schema)
        cfg_path = ROOT / "projects" / project_id / "shorts" / f"{video_id}.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(cfg_path)
    cfg: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    base_out = ROOT / "projects" / project_id / "output" / "longform" / video_id
    base_work = ROOT / "projects" / project_id / "work" / "longform" / video_id
    out_dir = base_out / language
    work_dir = base_work / language
    for d in (out_dir, work_dir, work_dir / "frames", work_dir / "narration", base_work / "panels"):
        d.mkdir(parents=True, exist_ok=True)

    # 1. TTS
    narration_cfg = sg._lang_field(cfg, language, "narration")
    if not narration_cfg or isinstance(narration_cfg, str):
        raise ValueError(f"{video_id}: no narration for language={language}")
    voice_speed = sg._lang_field(cfg, language, "voice_speed")
    segments = sg._build_segments(project, narration_cfg, work_dir, force,
                                  speed=voice_speed, language=language, speaker=speaker)
    narration_total = segments[-1].end if segments else 0.0
    print(f"  [landscape] {len(segments)} segments  total={narration_total:.1f}s")

    narration_mp3 = out_dir / "narration.mp3"
    if force or not narration_mp3.exists():
        sg._concat_mp3s([work_dir / "narration" / f"seg_{i:02d}.mp3" for i in range(len(segments))], narration_mp3)

    # 2. Resolve landscape panels (16:9)
    panel_cfgs = cfg["panels"]
    image_style = cfg.get("image_style", "anime")
    panel_id_to_path: dict[str, Path] = {}
    for idx, pc in enumerate(panel_cfgs):
        pid = pc["id"] if isinstance(pc, dict) and "id" in pc else f"p{idx + 1}"
        cache_key = pid if (isinstance(pc, dict) and "id" in pc) else idx
        panel_id_to_path[pid] = _resolve_landscape_panel(
            project_id, cache_key, pc["prompt"], base_work, force=force, image_style=image_style)

    # 3. panel slots in narration order (v2) + scene labels
    raw_panels: list[sg.PanelSlot] = []
    scene_labels: list[str | None] = []
    for i, seg_cfg in enumerate(narration_cfg):
        ref = seg_cfg["panel"]
        raw_panels.append(sg.PanelSlot(panel_path=panel_id_to_path[ref],
                                       duration=float(seg_cfg.get("duration", 6.0))))
        scene_labels.append(seg_cfg.get("label"))
    panels = sg._scale_panel_durations(raw_panels, narration_total)
    print(f"  panels: {len(panels)}")

    # 4. timeline + 5. render frames (lower-third subtitle, optional scene label)
    tiles = sg._build_timeline(panels, segments)
    # map each tile back to its scene label by start time → segment index
    seg_starts = [s.start for s in segments]
    tile_frames: list[tuple[Path, float]] = []
    for i, (start, end, ppath, cap) in enumerate(tiles):
        # nearest segment whose start <= tile start
        si = max([k for k, st in enumerate(seg_starts) if st <= start + 1e-6] or [0])
        frame_path = work_dir / "frames" / f"tile_{i:03d}.png"
        _compose_landscape_frame(ppath, frame_path, subtitle=cap, scene_label=scene_labels[si])
        tile_frames.append((frame_path, end - start))

    # 6. ffmpeg assemble at 1920×1080
    out_mp4 = out_dir / "longform.mp4"
    cmd: list[str] = ["ffmpeg", "-y"]
    for frame, dur in tile_frames:
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(frame)]
    cmd += ["-i", str(narration_mp3)]
    parts = [f"[{i}:v]scale={LW}:{LH}:flags=lanczos,setsar=1,fps={FPS}[v{i}]" for i in range(len(tile_frames))]
    concat_v = "".join(f"[v{i}]" for i in range(len(tile_frames)))
    parts.append(f"{concat_v}concat=n={len(tile_frames)}:v=1:a=0[vout]")
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[vout]", "-map", f"{len(tile_frames)}:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart",
        str(out_mp4),
    ]
    sg._ffmpeg(cmd)
    size = out_mp4.stat().st_size // (1024 * 1024)
    print(f"\n✅ {out_mp4}  ({narration_total:.1f}s, {size} MB)")
    return out_mp4


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("video_id")
    p.add_argument("--force", action="store_true")
    p.add_argument("--language", default="ja")
    p.add_argument("--speaker", default=None)
    args = p.parse_args()
    build_longform(args.project_id, args.video_id, force=args.force,
                   language=args.language, speaker=args.speaker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
