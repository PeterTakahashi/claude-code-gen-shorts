"""Build the chapter video: 16:9 still cuts + master audio + PIL-rendered subtitles.

This pipeline replaces the older webtoon hold-then-scroll flow:
  1. For each panel × each of its subtitles, generate a padded canvas PNG with
     the subtitle text baked in (white with black outline, bottom-center).
  2. Build a silent video clip for each subtitle window of duration = end-start.
  3. For panels without subtitles (silent), build a single silent clip whose
     duration equals the voice mp3 length.
  4. Concat all clips into work/silent_chapter.mp4 (no audio).
  5. Mux master audio onto the silent chapter → output/<chapter>/master.mp4.
  6. Also emit output/<chapter>/subtitles.srt as a sidecar.

Why PIL and not ffmpeg's `subtitles` filter?
  Most macOS Homebrew ffmpeg builds ship without libass — the `subtitles`
  filter then fails with "No such filter: 'subtitles'". PIL handles Japanese
  text via Hiragino Mincho ProN out of the box.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .project import Chapter, ProjectContext, load
from .render_panels import resolve_reuse_from


CANVAS_W = 1920
CANVAS_H = 1080
FPS = 30

# Subtitle font — Noto Sans JP (downloaded under assets/fonts/).
# Falls back to Hiragino if the Noto file is missing.
_NOTO_JP_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansJP-Regular.otf"
DEFAULT_SUB_FONT_PATH = str(_NOTO_JP_PATH) if _NOTO_JP_PATH.exists() else "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
DEFAULT_SUB_FONT_INDEX = 0
DEFAULT_SUB_FONT_SIZE = 44
SUB_LINE_GAP_PX = 12
SUB_BOTTOM_MARGIN_PX = 80
SUB_MAX_WIDTH_RATIO = 0.86

# Subtitle band styling: solid black box behind the text, white glyphs on top,
# no per-character stroke. Padding is added around the text bbox.
SUB_BOX_PADDING_X = 24
SUB_BOX_PADDING_Y = 12
SUB_BOX_FILL = (0, 0, 0)         # solid black
SUB_TEXT_FILL = (255, 255, 255)  # white


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(args[:8])} …\n{r.stderr[-1500:]}")


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# ---------- panel canvas + subtitle compositing ----------

def _pad_to_canvas(src: Path, dst: Path, *, force: bool = False) -> Path:
    if dst.exists() and not force:
        return dst
    img = Image.open(src).convert("RGB")
    sw, sh = img.size
    scale = min(CANVAS_W / sw, CANVAS_H / sh)
    nw, nh = int(round(sw * scale)), int(round(sh * scale))
    nw -= nw % 2
    nh -= nh % 2
    resized = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    canvas.paste(resized, ((CANVAS_W - nw) // 2, (CANVAS_H - nh) // 2))
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, format="PNG")
    return dst


def _wrap_japanese(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Greedy character wrap for Japanese text (no spaces between words)."""
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        bbox = draw.textbbox((0, 0), candidate, font=font)
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _composite_subtitle(canvas_img: Image.Image, text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Bake `text` onto the bottom-center of `canvas_img`.

    Style: solid black rectangle behind the text block, white glyphs on top,
    no per-character outline. Padding added around the bbox so glyphs don't
    touch the box edges.
    """
    out = canvas_img.copy()
    if not text.strip():
        return out

    draw = ImageDraw.Draw(out)
    max_width = int(CANVAS_W * SUB_MAX_WIDTH_RATIO)
    lines = _wrap_japanese(text, font, max_width, draw)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + SUB_LINE_GAP_PX
    total_text_h = line_h * len(lines)

    # Widest line determines box width.
    widest = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        if w > widest:
            widest = w

    box_w = widest + SUB_BOX_PADDING_X * 2
    box_h = total_text_h + SUB_BOX_PADDING_Y * 2
    box_x = (CANVAS_W - box_w) // 2
    box_y = CANVAS_H - SUB_BOTTOM_MARGIN_PX - box_h

    # Draw solid black box (subtitle band).
    draw.rectangle(
        (box_x, box_y, box_x + box_w, box_y + box_h),
        fill=SUB_BOX_FILL,
    )

    # Draw text lines centered horizontally inside the box, no stroke.
    text_y0 = box_y + SUB_BOX_PADDING_Y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (CANVAS_W - line_w) // 2
        y = text_y0 + i * line_h
        draw.text((x, y), line, font=font, fill=SUB_TEXT_FILL)

    return out


def _resolve_panel_image(project: ProjectContext, chapter: Chapter, panel: dict) -> Path | None:
    reuse = panel.get("reuse_from")
    if reuse:
        return resolve_reuse_from(project, chapter, reuse)
    pid = panel["panel_id"]
    scene_id = "_".join(pid.split("_")[:2])
    p = chapter.panels_dir / scene_id / f"{pid}_best.png"
    return p if p.exists() else None


# ---------- silent per-segment clips ----------

def _build_silent_clip(image: Path, duration_s: float, out: Path, *, force: bool = False) -> Path:
    if out.exists() and not force:
        return out
    if duration_s <= 0:
        # Skip negligible windows.
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{duration_s:.4f}", "-i", str(image),
        "-c:v", "libx264", "-tune", "stillimage", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-an",
        str(out),
    ])
    return out


def _concat_silent(clips: list[Path], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    list_path = out.with_suffix(".concat.txt")
    list_path.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clips),
        encoding="utf-8",
    )
    _ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c", "copy", str(out),
    ])
    return out


# ---------- SRT sidecar ----------

def _ts(s: float) -> str:
    if s < 0:
        s = 0.0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s - h * 3600 - m * 60
    whole = int(sec)
    ms = int(round((sec - whole) * 1000))
    if ms == 1000:
        whole += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{whole:02d},{ms:03d}"


def _write_srt(entries: list[dict], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, e in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{_ts(e['start_s'])} --> {_ts(e['end_s'])}")
        lines.append(e["text"])
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------- final assembly ----------

def _final_mux(silent_video: Path, master_audio: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([
        "ffmpeg", "-y",
        "-i", str(silent_video),
        "-i", str(master_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest",
        "-movflags", "+faststart",
        str(out),
    ])
    return out


# ---------- driver ----------

def build_chapter_video(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> Path:
    if not chapter.scenes_json.exists():
        raise FileNotFoundError(f"missing {chapter.scenes_json}")
    if not chapter.audio_master_wav.exists():
        raise FileNotFoundError(
            f"missing {chapter.audio_master_wav}. Run `audio_mixer` first."
        )

    scenes = json.loads(chapter.scenes_json.read_text(encoding="utf-8"))["scenes"]

    subs_data: dict = {}
    if chapter.subtitles_json.exists():
        subs_data = json.loads(chapter.subtitles_json.read_text(encoding="utf-8"))

    # Subtitle font — load once.
    sub_font = ImageFont.truetype(
        DEFAULT_SUB_FONT_PATH,
        size=DEFAULT_SUB_FONT_SIZE,
        index=DEFAULT_SUB_FONT_INDEX,
    )

    chapter.padded_panels_dir.mkdir(parents=True, exist_ok=True)
    chapter.video_clips_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: list[Path] = []
    srt_entries: list[dict] = []
    cumulative_chapter_s = 0.0

    for scene in scenes:
        for panel in scene["panels"]:
            pid = panel["panel_id"]
            img = _resolve_panel_image(project, chapter, panel)
            if img is None:
                print(f"  ⚠ skip {pid}: panel image missing")
                continue
            voice_mp3 = chapter.audio_dir / f"{pid}.mp3"
            if not voice_mp3.exists():
                print(f"  ⚠ skip {pid}: voice mp3 missing")
                continue

            voice_dur = _ffprobe_duration(voice_mp3)
            panel_subs = (subs_data.get(pid) or {}).get("bubbles") or []

            # Always pad the bare canvas (used for sub-less windows).
            base_padded = chapter.padded_panels_dir / f"{pid}.png"
            _pad_to_canvas(img, base_padded, force=force)
            base_canvas = Image.open(base_padded).convert("RGB")

            print(f"  [{pid}]  voice={voice_dur:.2f}s  subs={len(panel_subs)}")

            if not panel_subs:
                # Silent panel — single clip, full voice duration.
                clip = chapter.video_clips_dir / f"{pid}.mp4"
                _build_silent_clip(base_padded, voice_dur, clip, force=force)
                clip_paths.append(clip)
                cumulative_chapter_s += voice_dur
                continue

            # Build per-subtitle clip; cover gaps with the bare canvas.
            cursor = 0.0
            for j, sub in enumerate(panel_subs):
                sub_start = max(0.0, float(sub["start_s"]))
                sub_end = min(voice_dur, float(sub["end_s"]))
                if sub_end <= sub_start:
                    continue

                # Pre-sub gap
                if sub_start > cursor + 0.02:
                    gap_dur = sub_start - cursor
                    gap_clip = chapter.video_clips_dir / f"{pid}_gap{j}.mp4"
                    _build_silent_clip(base_padded, gap_dur, gap_clip, force=force)
                    clip_paths.append(gap_clip)
                    cursor = sub_start

                # Sub window
                sub_canvas_path = chapter.padded_panels_dir / f"{pid}_sub{j}.png"
                if not sub_canvas_path.exists() or force:
                    composited = _composite_subtitle(base_canvas, sub["text"], sub_font)
                    composited.save(sub_canvas_path, format="PNG")
                sub_dur = sub_end - sub_start
                sub_clip = chapter.video_clips_dir / f"{pid}_sub{j}.mp4"
                _build_silent_clip(sub_canvas_path, sub_dur, sub_clip, force=force)
                clip_paths.append(sub_clip)

                srt_entries.append({
                    "start_s": cumulative_chapter_s + sub_start,
                    "end_s": cumulative_chapter_s + sub_end,
                    "text": sub["text"],
                })
                cursor = sub_end

            # Tail gap
            if cursor < voice_dur - 0.02:
                tail_dur = voice_dur - cursor
                tail_clip = chapter.video_clips_dir / f"{pid}_tail.mp4"
                _build_silent_clip(base_padded, tail_dur, tail_clip, force=force)
                clip_paths.append(tail_clip)

            cumulative_chapter_s += voice_dur

    if not clip_paths:
        raise RuntimeError("no clips built — abort")

    silent_video = chapter.silent_chapter_mp4
    if not silent_video.exists() or force:
        _concat_silent(clip_paths, silent_video)
    print(f"\n  silent chapter video: {silent_video}  ({_ffprobe_duration(silent_video):.2f}s, {len(clip_paths)} clips)")

    srt_path = _write_srt(srt_entries, chapter.subtitles_srt)
    print(f"  subtitles sidecar:    {srt_path}  ({len(srt_entries)} entries)")

    out_path = chapter.master_mp4
    _final_mux(silent_video, chapter.audio_master_wav, out_path)
    final_dur = _ffprobe_duration(out_path)
    size_mb = out_path.stat().st_size // (1024 * 1024)
    print(f"\n✅ {out_path}  ({final_dur:.1f}s, {size_mb} MB)")
    return out_path


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.video_assembler <project_id> <chapter_id> [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    build_chapter_video(project, chapter, force="--force" in sys.argv)


if __name__ == "__main__":
    main()
