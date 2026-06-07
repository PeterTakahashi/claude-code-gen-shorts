"""Build a 9:16 YouTube Short from a per-short YAML config.

Reads `projects/<project_id>/shorts/<short_id>.yaml`, produces:
  projects/<project_id>/output/shorts/<short_id>/
    ├─ short.mp4          (1080×1920 H.264, 25-45 sec, captions baked in)
    ├─ thumbnail.png      (1080×1920, first frame + hook caption)
    ├─ narration.mp3      (Aivis TTS, concatenated from per-segment audio)
    └─ frames/            (intermediate panel pngs)

Design:
  - Images stay STATIC (no Ken Burns / zoompan) — easier to read
  - Multiple panel cuts (typical 6-10 per short) ranging 2-8 seconds each
  - Top hook caption is persistent (the reason a viewer keeps watching)
  - Small series-brand line sits under the hook (lets viewers find related shorts)
  - Bottom caption changes with each narration segment, synced to audio

Usage:
  uv run python -m src.short_gen <project_id> <short_id>
  uv run python -m src.short_gen <project_id> --all
  uv run python -m src.short_gen <project_id> <short_id> --force
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .aivis import default_client as aivis_default_client

# ElevenLabs SFX (optional, only loaded if a video opts into sfx mixing)
try:
    from .elevenlabs_sfx import generate_sfx as _gen_sfx
except Exception:
    _gen_sfx = None  # type: ignore

# Per-theme default SFX prompts (used if yaml doesn't override).
THEME_SFX_DEFAULTS: dict[str, str] = {
    "war_history":         "Heavy artillery explosion, smoke and debris, war-zone ambient",
    "mystery":             "Tense suspenseful thriller stinger, low ominous rumble",
    "astronomy":           "Cosmic whoosh, deep space ambient, sci-fi intro",
    "animals":             "Mysterious deep-sea oceanic ambient with bubbles",
    "corporate_fall":      "Glass shattering, dramatic corporate-collapse stinger",
    "crypto_incidents":    "Digital crash, glitch fall, screen breaking",
    "japan_praise":        "Warm cheering crowd, gentle wind chime, uplifting",
    "artisan":             "Hammer striking anvil, traditional Japanese woodshop ambient",
    "serendipity":         "Magical realization chime, ah-ha moment, sparkle",
    "sports_legends":      "Stadium crowd roar, boxing bell, sports arena",
    "mens_love":           "Soft heartbeat, gentle romantic pulse",
    "math":                "Chalk striking blackboard, classroom intro",
    "science":             "Cosmic whoosh, scientific lab intro",
    "love_psych":          "Soft heartbeat, gentle pulse, intimate ambient",
    "startup_news":        "Digital tech notification, modern intro stinger",
    "biography":           "Cinematic stinger, dramatic biographical opening",
    "corporate_incidents": "Dark ominous stinger, breaking-news alert",
    "housing_regret":      "Heavy door slam echoing in an empty house, ominous low financial-dread rumble",
    "money_failure":       "Anxious mounting debt-spiral stinger, distant phone ringing, tense low cash-dread rumble",
}


def _theme_for_project(project_id: str) -> str | None:
    """Look up channel/series.theme for a project from DB. Returns None on miss."""
    try:
        from .db import connect
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT theme FROM series WHERE id = %s", (project_id,))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _resolve_backend(project_id: str, requested: str) -> str:
    """Map a --backend choice to a concrete backend.

    'auto' (default) uses Gemini/nanobanana for EVERY channel. Local FLUX.2 was
    retired 2026-05-26: the face/in-image-text quality needed so much manual QC
    that the "free" generation cost more time than it saved. 'gemini' and
    'flux2-local' are still honored if passed explicitly.
    """
    if requested in ("gemini", "flux2-local"):
        return requested
    return "gemini"
from .image_generator import generate_image, generate_images_batch, generate_images_flux2_batch
from .project import load
# Qwen3-TTS client used for non-Japanese, non-English languages (zh/ko/de/fr/...)
try:
    from .qwen_tts import default_client as qwen_default_client
except ImportError:
    qwen_default_client = None  # qwen_tts optional

# Kokoro-82M client used for English (more deterministic than Qwen3-TTS).
try:
    from .kokoro_tts import default_client as kokoro_default_client
except ImportError:
    kokoro_default_client = None  # kokoro_tts optional, only required if --language en

# Char description cache: {project_id: {char_id: combined_description_en}}
_CHAR_CACHE: dict[str, dict[str, str]] = {}


def _char_descriptions(project_id: str) -> dict[str, str]:
    if project_id in _CHAR_CACHE:
        return _CHAR_CACHE[project_id]
    chars_yaml = ROOT / "projects" / project_id / "characters.yaml"
    out: dict[str, str] = {}
    if chars_yaml.exists():
        data = yaml.safe_load(chars_yaml.read_text(encoding="utf-8")) or {}
        for c in data.get("characters", []):
            desc = c.get("description_en") or ""
            outfit = c.get("outfit_en") or ""
            out[c["id"]] = f"{desc}. Wearing: {outfit}" if outfit else desc
    _CHAR_CACHE[project_id] = out
    return out


VERTICAL_PROMPT_PREFIX_DEFAULT = (
    "Generate a SQUARE (1:1 aspect ratio, 1024x1024) image. "
    "Style: full-color modern anime / webtoon style, soft cel shading, expressive line art, "
    "cinematic lighting, biographical drama tone. "
    "Compose the subject filling the square frame edge-to-edge — the image will be placed "
    "as the center band of a vertical short video, with blurred bokeh padding above and below. "
    "Keep critical details (faces, subjects, key objects) centered. "
    "No text, no captions, no speech bubbles in the image. "
    "Scene: "
)

# Pre-built style variants. yaml can override via top-level `image_style` field.
VERTICAL_PROMPT_PREFIXES = {
    "anime": VERTICAL_PROMPT_PREFIX_DEFAULT,
    "photorealistic": (
        "Generate a SQUARE (1:1 aspect ratio, 1024x1024) image. "
        "Style: PHOTOREALISTIC cinematic photography. NOT anime, NOT illustration, "
        "NOT cartoon, NOT drawing. Real-world photograph, DSLR camera quality, "
        "natural lighting, real human subjects with realistic faces and skin texture, "
        "documentary photography feel. "
        "Compose the subject filling the square frame edge-to-edge — the image will be "
        "placed as the center band of a vertical short video, with blurred bokeh padding "
        "above and below. Keep critical details (faces, subjects, key objects) centered. "
        "No text, no captions, no speech bubbles in the image. "
        "Scene: "
    ),
}

# Backward-compat alias
VERTICAL_PROMPT_PREFIX = VERTICAL_PROMPT_PREFIX_DEFAULT

ROOT = Path(__file__).resolve().parent.parent
FONT_BOLD = ROOT / "assets" / "fonts" / "NotoSansJP-Bold.otf"
FONT_REG = ROOT / "assets" / "fonts" / "NotoSansJP-Regular.otf"

W, H = 1080, 1920
FPS = 30

# Shorts panels are square (1024²) placed BELOW the top hook-caption band so the
# caption never covers the subject's face. The hook band spans y≈200..~548
# (2-line hook); a square scaled to width 1080 is 1080 tall, so top=560 keeps it
# clear of the caption while leaving a bottom bokeh band. Above the caption is
# just blurred bokeh — no sharp image is rendered there (face-overlap fix + the
# square stays the cheapest gen size). None elsewhere = legacy centered behavior.
PANEL_IMG_TOP = 560


# ---------- panel preparation ----------

def _fit_vertical_with_blur(src_path: Path, out_path: Path, top_y: int | None = None) -> Path:
    """Place a source image into a 9:16 canvas:
    - the sharp band is the source (resized to fit width)
    - top/bottom strips are a Gaussian-blurred + slightly enlarged copy
      of the same image, giving the "fake bokeh" frame familiar on TikTok.

    top_y: y of the sharp band's top edge. None → vertically centered (legacy,
    used by the novel pipeline). For shorts pass PANEL_IMG_TOP so the band sits
    below the hook caption (keeps faces clear of the top text).
    """
    if out_path.exists():
        return out_path
    img = Image.open(src_path).convert("RGB")
    sw, sh = img.size
    band_h = int(round(sh * (W / sw)))
    band = img.resize((W, band_h), Image.LANCZOS)

    scale = max(W / sw, H / sh)
    bw, bh = int(round(sw * scale)), int(round(sh * scale))
    bg = img.resize((bw, bh), Image.LANCZOS)
    bg = bg.crop((
        (bw - W) // 2, (bh - H) // 2,
        (bw - W) // 2 + W, (bh - H) // 2 + H,
    ))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
    overlay = Image.new("RGB", (W, H), (0, 0, 0))
    bg = Image.blend(bg, overlay, 0.35)

    out = bg.copy()
    if top_y is None:
        band_y = (H - band_h) // 2
    else:
        band_y = max(0, min(top_y, H - band_h))  # clamp so the band stays on-canvas
    out.paste(band, (0, band_y))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path, format="PNG", optimize=True)
    return out_path


def _resolve_panel(project_id: str, source: str, work_dir: Path) -> Path:
    if source.startswith("reuse:"):
        rel = source[len("reuse:"):]
        parts = rel.split("/")
        if len(parts) != 3:
            raise ValueError(f"bad reuse spec: {source}")
        chapter_id, scene_id, panel_basename = parts
        src = ROOT / "projects" / project_id / "work" / "chapters" / chapter_id / "panels" / scene_id / f"{panel_basename}_best.png"
        if not src.exists():
            raise FileNotFoundError(f"source panel missing: {src}")
        out = work_dir / "panels" / f"{panel_basename}_v.png"
        return _fit_vertical_with_blur(src, out)
    else:
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(src)
        out = work_dir / "panels" / (src.stem + "_v.png")
        return _fit_vertical_with_blur(src, out)


def _fit_native_vertical(src_path: Path, out_path: Path) -> Path:
    """Native 9:16 image — resize directly to 1080×1920 (with letterbox pad if needed)."""
    if out_path.exists():
        return out_path
    img = Image.open(src_path).convert("RGB")
    sw, sh = img.size
    if sw == W and sh == H:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG", optimize=True)
        return out_path
    target_ratio = W / H
    src_ratio = sw / sh
    if abs(src_ratio - target_ratio) < 0.02:
        scaled = img.resize((W, H), Image.LANCZOS)
    else:
        # Cover-fit (crop edges) so frame is filled — Gemini sometimes returns 1024×1024
        scale = max(W / sw, H / sh)
        nw, nh = int(round(sw * scale)), int(round(sh * scale))
        scaled = img.resize((nw, nh), Image.LANCZOS)
        x0, y0 = (nw - W) // 2, (nh - H) // 2
        scaled = scaled.crop((x0, y0, x0 + W, y0 + H))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scaled.save(out_path, format="PNG", optimize=True)
    return out_path


def _resolve_prompt_panel(
    project_id: str,
    panel_key: int | str,
    prompt: str,
    work_dir: Path,
    *,
    force: bool = False,
    image_style: str = "anime",
    image_ref: str | None = None,
) -> Path:
    """Call Gemini to generate a 9:16 vertical image from prompt, cache by panel_key.
    panel_key can be:
      - int (v1 positional): cache as gen_NN.png
      - str (v2 named id):   cache as gen_<id>.png  (kebab/snake case, no spaces)
    """
    if isinstance(panel_key, int):
        name = f"gen_{panel_key:02d}"
    else:
        # sanitize name to safe filename chars
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(panel_key))
        name = f"gen_{safe}"
    cache = work_dir / "panels" / f"{name}.png"
    fitted = work_dir / "panels" / f"{name}_fit.png"
    if fitted.exists() and not force:
        return fitted

    chars = _char_descriptions(project_id)
    # Expand {char_id} placeholders to full English descriptions for visual consistency
    expanded = prompt
    for cid, desc in chars.items():
        token = "{" + cid + "}"
        if token in expanded:
            expanded = expanded.replace(token, f"({desc})")
    prefix = VERTICAL_PROMPT_PREFIXES.get(image_style, VERTICAL_PROMPT_PREFIX_DEFAULT)
    full_prompt = prefix + expanded.strip()

    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or force:
        _backend = "flux2-local" if os.environ.get("IMAGE_BACKEND", "").lower() == "flux2-local" else "Gemini"
        # Optional: fetch a real-news reference image to ground the generation
        # (then nanobanana redraws an original — copyright-safe).
        refs: list[Path] = []
        if image_ref:
            try:
                from tools.news_image_ref import fetch_reference_image
            except Exception:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "_news_image_ref",
                    str(Path(__file__).resolve().parent.parent / "tools" / "news_image_ref.py"))
                _mod = importlib.util.module_from_spec(spec)  # type: ignore
                spec.loader.exec_module(_mod)  # type: ignore
                fetch_reference_image = _mod.fetch_reference_image
            ref_dir = work_dir / "panels" / "_refs"
            ref_path = fetch_reference_image(image_ref, out_dir=ref_dir)
            if ref_path:
                refs.append(ref_path)
        print(f"    generating panel {panel_key} via {_backend} (style={image_style}"
              f"{', ref=yes' if refs else ''}) …")
        generate_image(full_prompt, cache, reference_images=refs or None)
    # Place the square source BELOW the top hook-caption band (PANEL_IMG_TOP) and
    # blur-pad above/below, so the caption sits on bokeh and never covers faces.
    return _fit_vertical_with_blur(cache, fitted, top_y=PANEL_IMG_TOP)


# ---------- text rendering ----------

def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    fp = FONT_BOLD if (bold and FONT_BOLD.exists()) else FONT_REG
    return ImageFont.truetype(str(fp), size)


def _has_cjk(text: str) -> bool:
    """True if text contains any CJK character (Hiragana, Katakana, Han, etc.).
    Such text never splits on whitespace cleanly — must use char-wrap."""
    for c in text:
        cp = ord(c)
        if (0x3040 <= cp <= 0x30FF or       # Hiragana + Katakana
            0x3400 <= cp <= 0x4DBF or       # CJK Ext A
            0x4E00 <= cp <= 0x9FFF or       # CJK Unified
            0xF900 <= cp <= 0xFAFF or       # CJK Compat
            0xFF00 <= cp <= 0xFFEF):        # Halfwidth/Fullwidth (incl. 、。)
            return True
    return False


def _wrap_jp(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Text wrap.
    - Pure ASCII (no CJK) → word-boundary wrap.
    - Mixed or pure CJK → char-boundary wrap (Japanese has no internal spaces;
      using `split()` would treat the entire sentence as one unbreakable token).
    """
    if not _has_cjk(text):
        words = text.split()
        lines: list[str] = []
        current = ""
        for w in words:
            cand = (current + " " + w) if current else w
            bbox = draw.textbbox((0, 0), cand, font=font)
            if bbox[2] - bbox[0] > max_w and current:
                lines.append(current)
                current = w
            else:
                current = cand
        if current:
            lines.append(current)
        return lines

    # Has CJK: character-by-character (works for pure CJK and mixed JP/EN).
    lines = []
    current = ""
    for ch in text:
        cand = current + ch
        bbox = draw.textbbox((0, 0), cand, font=font)
        if bbox[2] - bbox[0] > max_w and current:
            lines.append(current)
            current = ch
        else:
            current = cand
    if current:
        lines.append(current)
    return lines


def _stroke_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
                 font: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int],
                 stroke_w: int = 3, stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255)) -> None:
    x, y = xy
    for dx in range(-stroke_w, stroke_w + 1):
        for dy in range(-stroke_w, stroke_w + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def _build_caption_overlay(
    *,
    hook_caption: str,
    series_brand: str | None,
    bottom_caption: str | None,
    date_overlay: str | None = None,
) -> Image.Image:
    """Build the transparent caption layer (top hook band + bottom caption band)
    as an RGBA 1080×1920 image. Reused by both the static frame compositor and the
    LTX video pipeline (where it overlays a moving panel clip)."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # --- top hook caption + small series brand ---
    hook_font = _load_font(92, bold=True)
    margin = 48
    hook_lines = _wrap_jp(draw, hook_caption, hook_font, W - margin * 2)
    hook_line_h = int(92 * 1.22)
    hook_total_h = hook_line_h * len(hook_lines)

    brand_h = 0
    if series_brand:
        brand_font = _load_font(38, bold=False)
        brand_h = int(38 * 1.6) + 8

    # Y offset 200 to clear iPhone Dynamic Island / status bar
    # (Pro Max devices use up to ~160px from top). Both video frames and the
    # derived thumbnail (which is just the first composed frame) get this.
    band_top = 200
    band_inner_pad = 28
    band_bottom = band_top + hook_total_h + brand_h + band_inner_pad * 2
    draw.rectangle([(0, band_top), (W, band_bottom)], fill=(0, 0, 0, 180))

    y = band_top + band_inner_pad
    for ln in hook_lines:
        bbox = draw.textbbox((0, 0), ln, font=hook_font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        _stroke_text(draw, (x, y), ln, hook_font, (255, 255, 255, 255), stroke_w=4)
        y += hook_line_h

    if series_brand:
        bb = draw.textbbox((0, 0), series_brand, font=brand_font)
        tw = bb[2] - bb[0]
        x = (W - tw) // 2
        draw.text((x, y + 4), series_brand, font=brand_font, fill=(210, 210, 210, 255))

    # --- top-right date overlay (news-style "MM/dd") ---
    if date_overlay:
        date_font = _load_font(56, bold=True)
        # bbox gives the visible-pixel extent when drawn at (0,0); use it to
        # center the text inside a uniform-padded badge (text was visually
        # high in the rectangle before — bb[1] offset wasn't compensated).
        bb = draw.textbbox((0, 0), date_overlay, font=date_font)
        text_w = bb[2] - bb[0]
        text_h = bb[3] - bb[1]
        pad_x, pad_y = 24, 14
        rect_w = text_w + pad_x * 2
        rect_h = text_h + pad_y * 2
        # Clear of Dynamic Island; flush to upper-right with small margin.
        rect_x = W - rect_w - 32
        rect_y = 96
        draw.rectangle(
            [(rect_x, rect_y), (rect_x + rect_w, rect_y + rect_h)],
            fill=(196, 30, 30, 225),
        )
        # Center text inside the rectangle (compensate for bbox offsets).
        text_x = rect_x + (rect_w - text_w) // 2 - bb[0]
        text_y = rect_y + (rect_h - text_h) // 2 - bb[1]
        _stroke_text(draw, (text_x, text_y), date_overlay, date_font,
                     (255, 255, 255, 255), stroke_w=2)

    # --- bottom caption (dynamic, swaps with narration) ---
    if bottom_caption:
        cap_font = _load_font(64, bold=True)
        cap_lines = _wrap_jp(draw, bottom_caption, cap_font, W - margin * 2)
        cap_line_h = int(64 * 1.3)
        cap_total = cap_line_h * len(cap_lines)
        pad = 24
        band_y0 = H - 280 - cap_total
        draw.rectangle(
            [(0, band_y0 - pad), (W, band_y0 + cap_total + pad)],
            fill=(0, 0, 0, 190),
        )
        y = band_y0
        for ln in cap_lines:
            bbox = draw.textbbox((0, 0), ln, font=cap_font)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            _stroke_text(draw, (x, y), ln, cap_font, (255, 255, 255, 255), stroke_w=3)
            y += cap_line_h

    return overlay


def _compose_frame(
    base_panel_path: Path,
    out_path: Path,
    *,
    hook_caption: str,
    series_brand: str | None,
    bottom_caption: str | None,
    date_overlay: str | None = None,
) -> Path:
    """Render one final 1080×1920 frame: panel + persistent top hook + dynamic bottom caption."""
    img = Image.open(base_panel_path).convert("RGBA")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    overlay = _build_caption_overlay(
        hook_caption=hook_caption, series_brand=series_brand,
        bottom_caption=bottom_caption, date_overlay=date_overlay,
    )
    composed = Image.alpha_composite(img, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(out_path, format="PNG", optimize=True)
    return out_path


def _compose_end_card(out_path: Path, series_brand: str, sub_text: str | None) -> Path:
    """Quiet sign-off card — just the series name, no CTA pressure."""
    img = Image.new("RGB", (W, H), (12, 12, 18))
    draw = ImageDraw.Draw(img)

    font = _load_font(108, bold=True)
    lines = _wrap_jp(draw, series_brand, font, W - 80)
    line_h = int(108 * 1.3)
    total_h = line_h * len(lines)
    y0 = (H - total_h) // 2 - 40
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        draw.text((x, y0), ln, font=font, fill=(245, 245, 245))
        y0 += line_h

    if sub_text:
        sub_font = _load_font(40, bold=False)
        sb = draw.textbbox((0, 0), sub_text, font=sub_font)
        tw = sb[2] - sb[0]
        draw.text(((W - tw) // 2, y0 + 30), sub_text, font=sub_font, fill=(170, 170, 175))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)
    return out_path


# ---------- TTS ----------

def _tts_segment(
    project, text: str, out_path: Path, *,
    force: bool = False, speed: float | None = None,
    pitch: float | None = None,
    language: str = "ja", speaker: str | None = None,
) -> Path:
    """Route TTS by language:
      ja → Aivis (VOICEVOX-style, port 10101)
      en → Kokoro-82M (port 10103), voice default 'am_michael' (US accent)
      other (zh/ko/de/fr/...) → Qwen3-TTS (port 10102), default speaker 'Ryan'
    """
    if out_path.exists() and not force:
        return out_path
    if language == "ja":
        style_id = int(project.narrator_voice_style_id or 0)
        actual_speed = float(speed) if speed is not None else float(project.narrator_voice_speed or 1.0)
        actual_pitch = float(pitch) if pitch is not None else float(
            getattr(project, "narrator_voice_pitch", 0.0) or 0.0)
        client = aivis_default_client()
        client.synthesize(text=text, speaker=style_id, out_path=out_path,
                          speed=actual_speed, pitch=actual_pitch)
    elif language == "en":
        if kokoro_default_client is None:
            raise RuntimeError(
                "Kokoro-82M client not available — install httpx and start the server "
                "at tools/kokoro-tts/start.sh (port 10103)."
            )
        client = kokoro_default_client()
        voice = speaker or "am_michael"
        actual_speed = float(speed) if speed is not None else 1.0
        client.synthesize(text=text, out_path=out_path, voice=voice, speed=actual_speed, lang="a")
    else:
        if qwen_default_client is None:
            raise RuntimeError(
                "Qwen3-TTS client not available — install httpx and start the server "
                "at tools/qwen-tts/start.sh (port 10102)."
            )
        client = qwen_default_client()
        qwen_lang_map = {"zh": "Chinese", "ja": "Japanese", "ko": "Korean",
                         "de": "German", "fr": "French", "ru": "Russian",
                         "pt": "Portuguese", "es": "Spanish", "it": "Italian"}
        qwen_lang = qwen_lang_map.get(language, "English")
        spk = speaker or "Ryan"
        client.synthesize(text=text, out_path=out_path, speaker=spk, language=qwen_lang)
    return out_path


def _concat_mp3s(paths: list[Path], out_path: Path) -> Path:
    """Concatenate mp3 segments via the concat demuxer with stream copy.
    Avoids the libmp3lame 'inadequate AVFrame plane padding' error that the
    concat filter + re-encode path hits when adjacent TTS segments have slight
    bitrate / format variations (which Aivis sometimes produces).
    """
    list_file = out_path.with_suffix(".concat.txt")
    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in paths),
        encoding="utf-8",
    )
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
           "-c", "copy", str(out_path)]
    try:
        _ffmpeg(cmd)
    finally:
        list_file.unlink(missing_ok=True)
    return out_path


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed: {' '.join(args[:6])} …")


def _ffprobe_duration(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# ---------- timeline assembly ----------

@dataclass
class Segment:
    text: str
    caption: str
    start: float
    end: float


@dataclass
class PanelSlot:
    panel_path: Path
    duration: float


def _build_segments(
    project, narration_cfg: list[dict], work_dir: Path, force: bool,
    speed: float | None = None, pitch: float | None = None,
    language: str = "ja", speaker: str | None = None,
) -> list[Segment]:
    """TTS each narration segment, return Segment list with start/end times."""
    mp3_paths: list[Path] = []
    for i, seg in enumerate(narration_cfg):
        out = work_dir / "narration" / f"seg_{i:02d}.mp3"
        _tts_segment(project, seg["text"], out, force=force, speed=speed,
                     pitch=pitch, language=language, speaker=speaker)
        mp3_paths.append(out)

    segments: list[Segment] = []
    cur = 0.0
    for seg, mp3 in zip(narration_cfg, mp3_paths):
        dur = _ffprobe_duration(mp3)
        segments.append(Segment(
            text=seg["text"],
            caption=seg.get("caption", seg["text"]),
            start=cur,
            end=cur + dur,
        ))
        cur += dur
    return segments


def _scale_panel_durations(panels: list[PanelSlot], target_total: float) -> list[PanelSlot]:
    """Scale per-panel durations so their sum matches target_total."""
    current = sum(p.duration for p in panels)
    if current <= 0 or abs(current - target_total) < 0.05:
        return panels
    factor = target_total / current
    return [PanelSlot(panel_path=p.panel_path, duration=p.duration * factor) for p in panels]


def _apply_opening_cut(panels: list[PanelSlot], opening_cut: float) -> list[PanelSlot]:
    """Make the very first image switch fast so viewers don't read the short as a
    static slideshow and swipe away in the first ~2s. Caps image #1 at
    `opening_cut` seconds, then cuts to image #2 for the rest of the first
    narration segment. Total duration is preserved (audio stays in sync)."""
    if opening_cut <= 0 or len(panels) < 2:
        return panels
    first = panels[0]
    # Already short enough — leave it.
    if first.duration <= opening_cut + 0.3:
        return panels
    head = PanelSlot(panel_path=first.panel_path, duration=opening_cut)
    tail = PanelSlot(panel_path=panels[1].panel_path, duration=first.duration - opening_cut)
    return [head, tail] + panels[1:]


def _build_timeline(panels: list[PanelSlot], segments: list[Segment]) -> list[tuple[float, float, Path, str | None]]:
    """Compute (start, end, panel_path, bottom_caption) tiles.

    Cut points are the union of panel boundaries and segment boundaries.
    For each (panel, segment) overlap window, emit a tile.
    """
    panel_boundaries: list[tuple[float, float, Path]] = []
    t = 0.0
    for p in panels:
        panel_boundaries.append((t, t + p.duration, p.panel_path))
        t += p.duration
    total_panel_t = t

    MIN_TILE_S = 0.10  # filter out near-zero slivers that would loop infinitely in ffmpeg
    tiles: list[tuple[float, float, Path, str | None]] = []
    for ps, pe, ppath in panel_boundaries:
        if pe - ps < MIN_TILE_S:
            continue
        overlapping_segs = [s for s in segments if s.end > ps and s.start < pe]
        if not overlapping_segs:
            tiles.append((ps, pe, ppath, None))
            continue
        boundaries = sorted({ps, pe} | {s.start for s in overlapping_segs} | {s.end for s in overlapping_segs})
        boundaries = [b for b in boundaries if ps <= b <= pe]
        for a, b in zip(boundaries[:-1], boundaries[1:]):
            if b - a < MIN_TILE_S:
                continue
            mid = (a + b) / 2
            seg_at_mid = next((s for s in segments if s.start <= mid < s.end), None)
            cap = seg_at_mid.caption if seg_at_mid else None
            tiles.append((a, b, ppath, cap))
    return tiles


# ---------- main build ----------

def _is_v2(cfg: dict) -> bool:
    """v2 schema: top-level language section (en/ja/...) AND panel-id refs in narration."""
    for lang in ("en", "ja", "zh", "ko", "de", "fr", "es"):
        if isinstance(cfg.get(lang), dict) and "narration" in cfg[lang]:
            return True
    # Also: panels with explicit `id` field (even if only one lang)
    if cfg.get("panels") and isinstance(cfg["panels"], list):
        if any(isinstance(p, dict) and "id" in p for p in cfg["panels"]):
            return True
    return False


def _lang_field(cfg: dict, language: str, field: str, *fallback_fields: str):
    """Get a field for `language` from the yaml.

    Lookup order:
      1. v2 schema: cfg[language][field]
      2. v1 schema: cfg['i18n'][language][field]
      3. v1 suffix style: cfg[f'{field}_{language}']
      4. top-level cfg[field] (assumed JA in v1)
      5. each name in fallback_fields, then None
    """
    # v2: top-level language section
    lang_section = cfg.get(language)
    if isinstance(lang_section, dict) and field in lang_section:
        return lang_section[field]
    # v1: i18n.<lang>.<field>
    i18n = (cfg.get("i18n") or {}).get(language, {})
    if field in i18n:
        return i18n[field]
    suffix_key = f"{field}_{language}"
    if suffix_key in cfg:
        return cfg[suffix_key]
    if field in cfg:
        return cfg[field]
    for fb in fallback_fields:
        if fb in cfg:
            return cfg[fb]
    return None


def build_short(project_id: str, short_id: str, *, force: bool = False, language: str = "ja",
                speaker: str | None = None) -> Path:
    project = load(project_id)
    cfg_path = ROOT / "projects" / project_id / "shorts" / f"{short_id}.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(cfg_path)
    cfg: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    # Path layout: language always lives in its own subfolder.
    #   output/shorts/<sid>/<lang>/short.mp4
    #   work/shorts/<sid>/<lang>/   (per-language tile frames, narration mp3s)
    #   work/shorts/<sid>/panels/   (language-neutral panel image cache)
    base_out = ROOT / "projects" / project_id / "output" / "shorts" / short_id
    base_work = ROOT / "projects" / project_id / "work" / "shorts" / short_id
    out_dir = base_out / language
    work_dir = base_work / language
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "frames").mkdir(parents=True, exist_ok=True)
    # Panels are language-agnostic — share between languages by using the base panels dir
    panels_dir = base_work / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "narration").mkdir(parents=True, exist_ok=True)

    hook_caption = _lang_field(cfg, language, "hook_caption")
    series_brand = _lang_field(cfg, language, "series_brand", "cta_caption")
    # Optional top-right MM/dd date badge ("news-style"). yaml: date_overlay: auto | "05/29" | null
    date_field = cfg.get("date_overlay") or _lang_field(cfg, language, "date_overlay")
    if date_field == "auto" or date_field is True:
        from datetime import datetime
        date_overlay = datetime.now().strftime("%m/%d")
    elif isinstance(date_field, str) and date_field:
        date_overlay = date_field
    else:
        date_overlay = None
    # End card defaults to OFF because YouTube Shorts loops the video; a clear
    # ending invites viewers to swipe away. The hook image at the start IS the
    # ending visually — loop-friendly. Set end_duration > 0 if you really want
    # a brand sign-off (not recommended).
    end_brand = cfg.get("end_brand")
    end_sub = cfg.get("end_sub")
    end_duration = float(cfg.get("end_duration", 0.0))

    # 1. TTS each segment + measure (language-aware)
    narration_cfg = _lang_field(cfg, language, "narration")
    if isinstance(narration_cfg, str) or not narration_cfg:
        raise ValueError(
            f"{short_id}: no narration found for language={language}. "
            f"Add `narration` (ja default) or `i18n.{language}.narration` to the yaml."
        )
    voice_speed = _lang_field(cfg, language, "voice_speed")
    voice_pitch = _lang_field(cfg, language, "voice_pitch")
    segments = _build_segments(
        project, narration_cfg, work_dir, force,
        speed=voice_speed, pitch=voice_pitch,
        language=language, speaker=speaker,
    )
    narration_total = segments[-1].end if segments else 0.0
    print(f"  language: {language}  narration: {len(segments)} segments  total={narration_total:.1f}s")

    # 2. Concatenate per-segment mp3s into one narration.mp3
    narration_mp3 = out_dir / "narration.mp3"
    if force or not narration_mp3.exists():
        _concat_mp3s([work_dir / "narration" / f"seg_{i:02d}.mp3" for i in range(len(segments))], narration_mp3)

    # 2b. Generate + mix opening SFX under the first ~5 sec of narration.
    # Skipped silently if ELEVEN_LABS_API_KEY not set or sfx client unavailable.
    sfx_prompt = (cfg.get(language, {}) or {}).get("sfx_prompt") or cfg.get("sfx_prompt")
    if not sfx_prompt:
        theme = _theme_for_project(project_id)
        sfx_prompt = THEME_SFX_DEFAULTS.get(theme or "", None)
    sfx_duration = float((cfg.get(language, {}) or {}).get("sfx_duration") or cfg.get("sfx_duration") or 5.0)
    sfx_volume = float((cfg.get(language, {}) or {}).get("sfx_volume") or cfg.get("sfx_volume") or 0.08)  # ~-22dB

    narration_with_sfx = narration_mp3
    if sfx_prompt and _gen_sfx is not None and os.environ.get("ELEVEN_LABS_API_KEY"):
        sfx_path = work_dir / "sfx.mp3"
        mixed_path = out_dir / "narration_with_sfx.mp3"
        if force or not sfx_path.exists():
            try:
                print(f"  generating SFX: {sfx_prompt[:60]!r} ({sfx_duration:.1f}s)")
                _gen_sfx(sfx_prompt, sfx_path, duration_seconds=sfx_duration)
            except Exception as e:
                print(f"  ⚠️ SFX generation failed ({e}); skipping", file=sys.stderr)
                sfx_path = None  # type: ignore
        if sfx_path and sfx_path.exists() and (force or not mixed_path.exists()):
            # Mix SFX under narration: volume=sfx_volume, fade out the last 1s of SFX,
            # narration is loudest. duration=longest keeps full narration.
            fade_start = max(0.0, sfx_duration - 1.0)
            cmd_mix = [
                "ffmpeg", "-y",
                "-i", str(narration_mp3),
                "-i", str(sfx_path),
                "-filter_complex",
                f"[1]volume={sfx_volume},afade=t=out:st={fade_start:.2f}:d=1.0,adelay=0|0[sfx];"
                f"[0][sfx]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.98",
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(mixed_path),
            ]
            try:
                _ffmpeg(cmd_mix)
                narration_with_sfx = mixed_path
            except Exception as e:
                print(f"  ⚠️ SFX mix failed ({e}); falling back to narration only", file=sys.stderr)
        elif mixed_path.exists():
            narration_with_sfx = mixed_path

    # 3. Resolve panel images.
    # v2: panels indexed by id; narration references panel by id; panel order in video = narration order.
    # v1: panels are positional, narration[i] pairs with panels[i].
    panel_cfgs = cfg["panels"]
    is_v2 = _is_v2(cfg)
    panel_work_dir = base_work  # shared panel cache for all languages
    image_style = cfg.get("image_style", "anime")  # yaml override: "photorealistic" | "anime"

    # Build a panel_id → image_path map
    panel_id_to_path: dict[str, Path] = {}
    for idx, pc in enumerate(panel_cfgs):
        if isinstance(pc, dict) and "id" in pc:
            pid = pc["id"]
        else:
            pid = f"p{idx + 1}"  # auto-id for v1 panels (also enables hybrid lookup)
        if "prompt" in pc:
            # Cache key is panel_id when present, else positional index (v1 compat keeps existing cache).
            cache_key = pid if "id" in pc else idx
            v_path = _resolve_prompt_panel(project_id, cache_key, pc["prompt"], panel_work_dir,
                                             force=force, image_style=image_style,
                                             image_ref=pc.get("image_ref"))
        elif "source" in pc:
            v_path = _resolve_panel(project_id, pc["source"], panel_work_dir)
        else:
            raise ValueError(f"panel '{pid}': needs either `prompt` (generate) or `source` (reuse)")
        panel_id_to_path[pid] = v_path

    raw_panels: list[PanelSlot] = []
    if is_v2:
        # v2: build panel list in narration order. Each narration entry references panel by id.
        for i, seg_cfg in enumerate(narration_cfg):
            if "panel" not in seg_cfg:
                raise ValueError(f"{short_id} v2: narration[{i}] missing required `panel` field "
                                 f"(reference an id from `panels`)")
            ref = seg_cfg["panel"]
            if ref not in panel_id_to_path:
                raise ValueError(f"{short_id}: narration[{i}].panel = {ref!r} but no such panel id. "
                                 f"Available: {list(panel_id_to_path.keys())}")
            # Per-segment duration follows the TTS audio (filled in next step via _scale)
            raw_panels.append(PanelSlot(
                panel_path=panel_id_to_path[ref],
                duration=float(seg_cfg.get("duration", 4.0)),
            ))
    else:
        # v1: positional pairing — panel[i] for narration[i]
        for idx, pc in enumerate(panel_cfgs):
            pid = pc.get("id", f"p{idx + 1}") if isinstance(pc, dict) else f"p{idx + 1}"
            raw_panels.append(PanelSlot(
                panel_path=panel_id_to_path[pid],
                duration=float(pc.get("duration", 4.0)) if isinstance(pc, dict) else 4.0,
            ))
    panels = _scale_panel_durations(raw_panels, narration_total)
    opening_cut = float(cfg.get("opening_cut", 1.5))
    panels = _apply_opening_cut(panels, opening_cut)
    print(f"  panels: {len(panels)} cuts  durations={[f'{p.duration:.1f}' for p in panels]}")

    # 4. Build tile timeline = (start, end, panel, bottom_caption)
    tiles = _build_timeline(panels, segments)
    print(f"  tiles: {len(tiles)}")

    # 5. Render every tile to a unique frame PNG (cached by tile signature)
    tile_frames: list[tuple[Path, float]] = []
    for i, (start, end, ppath, cap) in enumerate(tiles):
        frame_path = work_dir / "frames" / f"tile_{i:03d}.png"
        _compose_frame(
            ppath, frame_path,
            hook_caption=hook_caption,
            series_brand=series_brand,
            bottom_caption=cap,
            date_overlay=date_overlay,
        )
        tile_frames.append((frame_path, end - start))

    # 6. (Optional) End-brand card — defaults OFF for loop-friendly Shorts.
    if end_brand and end_duration > 0.05:
        end_card = work_dir / "frames" / "end_card.png"
        _compose_end_card(end_card, end_brand, end_sub)
        tile_frames.append((end_card, end_duration))

    # 7. Compose final video with ffmpeg
    out_mp4 = out_dir / "short.mp4"
    cmd: list[str] = ["ffmpeg", "-y"]
    for frame, dur in tile_frames:
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(frame)]
    cmd += ["-i", str(narration_with_sfx)]

    parts: list[str] = []
    for i, _ in enumerate(tile_frames):
        parts.append(f"[{i}:v]scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS}[v{i}]")
    concat_v = "".join(f"[v{i}]" for i in range(len(tile_frames)))
    parts.append(f"{concat_v}concat=n={len(tile_frames)}:v=1:a=0[vout]")
    filtergraph = ";".join(parts)

    audio_idx = len(tile_frames)
    cmd += [
        "-filter_complex", filtergraph,
        "-map", "[vout]",
        "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    _ffmpeg(cmd)

    # 8. Thumbnail = first content tile, saved as JPEG (must be ≤2MB for YouTube)
    if tile_frames:
        first = Image.open(tile_frames[0][0]).convert("RGB")
        first.save(out_dir / "thumbnail.jpg", format="JPEG", quality=88, optimize=True)
        # also keep PNG for local inspection
        first.save(out_dir / "thumbnail.png", format="PNG", optimize=True)

    dur = _ffprobe_duration(out_mp4)
    size = out_mp4.stat().st_size // (1024 * 1024)
    print(f"\n✅ {out_mp4}  ({dur:.1f}s, {size} MB)")
    return out_mp4


def _collect_pending_panel_jobs(project_id: str, short_ids: list[str], *, force: bool) -> list[tuple[str, Path, str]]:
    """For each yaml short config, list (short_id, out_png_path, prompt) for panels
    whose generated file doesn't exist yet (or force=True). Used to pre-batch
    Gemini image generation across multiple shorts at once.
    """
    chars = _char_descriptions(project_id)
    jobs: list[tuple[str, Path, str]] = []
    for sid in short_ids:
        cfg_path = ROOT / "projects" / project_id / "shorts" / f"{sid}.yaml"
        if not cfg_path.exists():
            continue
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        work_dir = ROOT / "projects" / project_id / "work" / "shorts" / sid
        image_style = cfg.get("image_style", "anime")
        prefix = VERTICAL_PROMPT_PREFIXES.get(image_style, VERTICAL_PROMPT_PREFIX_DEFAULT)
        for idx, pc in enumerate(cfg.get("panels", [])):
            if "prompt" not in pc:
                continue
            # Cache key MUST match _resolve_prompt_panel: v2 (id present) → gen_<id>,
            # else positional gen_NN. Otherwise the batch writes gen_NN while the build
            # reads gen_<id> and the pre-generation is wasted (v2 bug).
            if isinstance(pc, dict) and "id" in pc:
                safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(pc["id"]))
                name = f"gen_{safe}"
            else:
                name = f"gen_{idx:02d}"
            cache = work_dir / "panels" / f"{name}.png"
            if cache.exists() and not force:
                continue
            expanded = pc["prompt"]
            for cid, desc in chars.items():
                tok = "{" + cid + "}"
                if tok in expanded:
                    expanded = expanded.replace(tok, f"({desc})")
            full_prompt = prefix + expanded.strip()
            jobs.append((sid, cache, full_prompt))
    return jobs


def _batch_generate_panels(project_id: str, jobs: list[tuple[str, Path, str]], *, poll_interval_s: float = 30.0) -> int:
    """Submit one Gemini batch for all pending panel images across all shorts.
    Returns number of successfully written panels."""
    if not jobs:
        return 0
    batch_jobs = [(prompt, out_path, None) for (_sid, out_path, prompt) in jobs]
    flux2 = os.environ.get("IMAGE_BACKEND", "").lower() == "flux2-local"
    backend_name = "FLUX.2 local" if flux2 else "Gemini"
    print(f"\n=== {backend_name} batch: {len(jobs)} panel image(s) across {len({j[0] for j in jobs})} short(s) ===")
    batch_fn = generate_images_flux2_batch if flux2 else generate_images_batch
    written, failures = batch_fn(
        batch_jobs,
        poll_interval_s=poll_interval_s,
        display_name=f"shorts-{project_id}",
    )
    if failures:
        print(f"  ⚠️ {len(failures)} panel(s) failed in batch; will fall back to sequential per-short", file=sys.stderr)
        for idx, msg in failures[:5]:
            sid, out_path, _ = jobs[idx]
            print(f"    {sid}: {out_path.name}: {msg[:120]}", file=sys.stderr)
    return len(written)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("short_id", nargs="?", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--batch", action="store_true",
                   help="Use Gemini Batch API to generate all panel images at once (50%% off, ~20-60min wait). "
                        "Recommended for multi-short runs.")
    p.add_argument("--language", default="ja",
                   help="Language code for narration + captions (ja=Aivis, en/other=Qwen3-TTS). "
                        "Reads i18n.<lang>.* fields from yaml (falls back to top-level for ja).")
    p.add_argument("--speaker", default=None,
                   help="TTS speaker override. For en: 'Ryan' or 'Aiden' (Qwen3-TTS).")
    p.add_argument("--poll-interval", type=float, default=30.0)
    p.add_argument("--backend", choices=["auto", "gemini", "flux2-local"], default="auto",
                   help="Image backend. 'auto' (default) picks per channel theme: "
                        "likeness-heavy themes (biography/sports/incidents/war/startup) → "
                        "gemini, else local FLUX.2 (free). Overrides IMAGE_BACKEND env.")
    args = p.parse_args()

    # Resolve + apply image backend (sets IMAGE_BACKEND that image_generator reads).
    backend = _resolve_backend(args.project_id, args.backend)
    os.environ["IMAGE_BACKEND"] = backend
    print(f"  image backend: {backend} (--backend={args.backend}, theme={_theme_for_project(args.project_id)})")

    shorts_dir = ROOT / "projects" / args.project_id / "shorts"
    if args.all:
        ids = sorted(f.stem for f in shorts_dir.glob("*.yaml"))
        if not ids:
            print(f"no short configs under {shorts_dir}")
            return 1

        # Optionally pre-generate all panel images via a single batch.
        if args.batch:
            pending = _collect_pending_panel_jobs(args.project_id, ids, force=args.force)
            if pending:
                _batch_generate_panels(args.project_id, pending, poll_interval_s=args.poll_interval)
            else:
                print("  (no pending panels — all cached)")

        failures: list[tuple[str, str]] = []
        for sid in ids:
            print(f"\n=== {args.project_id}/{sid} ({args.language}) ===")
            try:
                build_short(args.project_id, sid, force=args.force,
                            language=args.language, speaker=args.speaker)
            except Exception as e:
                print(f"❌ {sid} FAILED: {e}", file=sys.stderr)
                failures.append((sid, str(e)))
        if failures:
            print(f"\n⚠️ {len(failures)} short(s) failed in {args.project_id}:", file=sys.stderr)
            for sid, err in failures:
                print(f"  - {sid}: {err[:200]}", file=sys.stderr)
    else:
        if not args.short_id:
            print("ERROR: short_id required (or --all)", file=sys.stderr)
            return 2
        # --batch works for a single short too: collect its panels and generate
        # them in one batch (esp. valuable for flux2-local = single model load).
        if args.batch:
            pending = _collect_pending_panel_jobs(args.project_id, [args.short_id], force=args.force)
            if pending:
                _batch_generate_panels(args.project_id, pending, poll_interval_s=args.poll_interval)
        build_short(args.project_id, args.short_id, force=args.force,
                    language=args.language, speaker=args.speaker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
