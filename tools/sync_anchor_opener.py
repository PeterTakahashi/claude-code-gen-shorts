#!/usr/bin/env python3
"""Prepend a Sync.so anchor talking-head opener to an existing short.mp4.

Pipeline:
  1. Slice the first N seconds of audio from the short
  2. Sync.so lipsync(announcer_image, sliced_audio) → opener.mp4
  3. Trim the short to start from N seconds in (visuals AND audio dropped)
  4. ffmpeg concat: opener.mp4 + trimmed_short.mp4 → final mp4
  5. Replace the original short.mp4 (optional --in-place) or write to --out

Usage:
  .venv/bin/python tools/sync_anchor_opener.py \\
    --image assets/anchor.png \\
    --short projects/news_test_1/output/shorts/<sid>/ja/short.mp4 \\
    --seconds 6 \\
    --in-place
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_lipsync import lipsync as sync_lipsync_fn       # noqa: E402
from heygen_lipsync import lipsync as heygen_lipsync_fn, DEFAULT_AVATAR_ID  # noqa: E402

FFMPEG = "/opt/homebrew/bin/ffmpeg"


def run(*args):
    """Run a subprocess command, raise on failure."""
    print(f"  $ {' '.join(str(a) for a in args)}", flush=True)
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed:\n  cmd={args}\n  stderr={r.stderr[-800:]}")
    return r


def extract_audio_segment(short: Path, seconds: float, out: Path):
    """Write the first <seconds> of audio from short.mp4 to out (mp3)."""
    run(FFMPEG, "-y", "-i", short, "-t", f"{seconds}", "-vn",
        "-c:a", "libmp3lame", "-b:a", "192k", out)


def image_to_video(image: Path, seconds: float, out: Path,
                   width: int = 1080, height: int = 1920, fps: int = 30):
    """Sync.so refuses still-image inputs to its 'video' field — wrap the
    announcer PNG into a short looped mp4 of the right duration & dimensions."""
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height},setsar=1")
    run(FFMPEG, "-y", "-loop", "1", "-i", image, "-t", f"{seconds}",
        "-vf", vf, "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out)


def trim_short(short: Path, start_seconds: float, out: Path):
    """Re-encode short.mp4 to start at start_seconds (keyframe-safe)."""
    run(FFMPEG, "-y", "-ss", f"{start_seconds}", "-i", short,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)


def normalize_opener(opener_in: Path, opener_out: Path,
                     target_w: int = 1080, target_h: int = 1920, fps: int = 30,
                     avatar_top_clear: int = 460):
    """Scale + pad the HeyGen/Sync.so opener output to 1080x1920@30fps AND
    shift the avatar down so its face stays below the title band (which lives
    around y=200..y=440 in the caption overlay). The freed top strip is filled
    with a heavily-blurred copy of the avatar for visual continuity, so the
    semi-transparent title band reads cleanly without cutting through the
    speaker's forehead."""
    main_h = target_h - avatar_top_clear
    filter_complex = (
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},setsar=1,fps={fps}[scaled];"
        f"[scaled]split=2[main][bg];"
        f"[bg]boxblur=30:2[bgblur];"
        f"[main]crop={target_w}:{main_h}:0:0[mainCrop];"
        f"[bgblur][mainCrop]overlay=0:{avatar_top_clear}[v]"
    )
    run(FFMPEG, "-y", "-i", opener_in,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", opener_out)


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["/opt/homebrew/bin/ffprobe", "-i", str(path), "-show_entries",
         "format=duration", "-v", "quiet", "-of", "csv=p=0"]).decode().strip()
    return float(out) if out else 0.0


def apply_captions_to_opener(opener: Path, short: Path,
                             opener_seconds: float, out: Path):
    """Composite the same top-hook + bottom-caption + date-badge overlays the
    main short uses onto each frame of the talking-head opener, switching the
    bottom caption per narration segment (so the opener matches the rest of
    the video stylistically)."""
    import yaml
    short = Path(short).resolve()
    # short.mp4 lives at projects/<proj>/output/shorts/<sid>/<lang>/short.mp4
    proj_dir = short.parents[4]                 # projects/<proj>/
    sid     = short.parents[1].name             # <sid>
    lang    = short.parents[0].name             # ja
    yaml_path = proj_dir / "shorts" / f"{sid}.yaml"
    work_dir  = proj_dir / "work" / "shorts" / sid / lang
    cfg = yaml.safe_load(open(yaml_path, encoding="utf-8"))
    lsec = cfg.get(lang) if isinstance(cfg.get(lang), dict) else {}

    def lf(field, default=None):
        v = lsec.get(field)
        return v if v is not None else cfg.get(field, default)

    hook = lf("hook_caption", "")
    brand = lf("series_brand", None)
    date_field = lf("date_overlay")
    if date_field in ("auto", True):
        from datetime import datetime
        date_str = datetime.now().strftime("%m/%d")
    elif isinstance(date_field, str) and date_field:
        date_str = date_field
    else:
        date_str = None

    narration = lf("narration", [])

    # Segment timings come from the cached per-segment mp3s in work_dir
    seg_times: list[tuple[float, float, str]] = []
    cur = 0.0
    for i, seg in enumerate(narration):
        seg_mp3 = work_dir / "narration" / f"seg_{i:02d}.mp3"
        if not seg_mp3.exists() or cur >= opener_seconds:
            break
        d = _ffprobe_duration(seg_mp3)
        end = min(cur + d, opener_seconds)
        seg_times.append((cur, end, seg.get("caption", "")))
        cur += d
    if not seg_times:
        shutil.copy(opener, out); return

    # Reuse the main short's caption overlay renderer for visual parity
    proj_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(proj_root))
    from src.short_gen import _build_caption_overlay  # type: ignore

    overlay_dir = out.parent / "caption_overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay_paths: list[Path] = []
    for i, (_s, _e, caption) in enumerate(seg_times):
        ov_img = _build_caption_overlay(
            hook_caption=hook, series_brand=brand,
            bottom_caption=caption, date_overlay=date_str,
        )
        p = overlay_dir / f"overlay_{i:02d}.png"
        ov_img.save(p)
        overlay_paths.append(p)

    inputs = ["-i", str(opener)]
    for p in overlay_paths:
        inputs.extend(["-loop", "1", "-i", str(p)])
    prev = "[0:v]"
    parts: list[str] = []
    for i, (start, end, _c) in enumerate(seg_times):
        lbl = f"[v{i+1}]"
        parts.append(
            f"{prev}[{i+1}:v]overlay=enable='between(t,{start:.3f},{end:.3f})'{lbl}"
        )
        prev = lbl
    filter_complex = ";".join(parts)

    run(FFMPEG, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", prev, "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-t", f"{opener_seconds:.3f}", str(out))


def concat_clips(a: Path, b: Path, out: Path):
    """Concatenate two clips using the concat filter (re-encode for safety)."""
    run(FFMPEG, "-y", "-i", a, "-i", b,
        "-filter_complex",
        "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="heygen", choices=["heygen", "sync"],
                    help="Lipsync backend (default heygen — sync.so handles still-image input poorly)")
    ap.add_argument("--image", type=Path, default=None,
                    help="[sync backend] Announcer portrait image (PNG/JPG)")
    ap.add_argument("--avatar-id", default=DEFAULT_AVATAR_ID,
                    help="[heygen backend] HeyGen avatar_id (default: news anchor)")
    ap.add_argument("--short", required=True, type=Path,
                    help="Existing short.mp4 to prepend the opener to")
    ap.add_argument("--seconds", type=float, default=6.0,
                    help="Seconds of opener / audio to lipsync (default 6)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path (default: alongside short, with _anchor suffix)")
    ap.add_argument("--in-place", action="store_true",
                    help="Replace the input short.mp4 with the result")
    ap.add_argument("--keep-tmp", action="store_true",
                    help="Keep intermediate files for inspection")
    args = ap.parse_args()

    if args.backend == "sync" and (not args.image or not args.image.is_file()):
        print(f"ERROR: sync backend needs --image", file=sys.stderr); return 1
    if not args.short.is_file():
        print(f"ERROR: short not found: {args.short}", file=sys.stderr); return 1

    out_path = args.out
    if not out_path:
        out_path = args.short.with_name(args.short.stem + "_anchor.mp4")

    with tempfile.TemporaryDirectory(prefix="anchor_opener_") as td:
        td = Path(td)
        opener_audio  = td / "opener.mp3"
        anchor_loop   = td / "anchor_loop.mp4"
        opener_raw    = td / "opener_raw.mp4"
        opener_norm   = td / "opener.mp4"
        trimmed       = td / "trimmed.mp4"
        final         = td / "final.mp4"

        print(f">>> 1) extracting first {args.seconds}s of audio")
        extract_audio_segment(args.short, args.seconds, opener_audio)
        if args.backend == "heygen":
            print(f">>> 2) HeyGen lipsync (avatar_id={args.avatar_id[:8]}… + audio)")
            heygen_lipsync_fn(args.avatar_id, opener_audio, opener_raw)
        else:
            print(f">>> 1b) wrapping announcer image into a looped mp4 (Sync.so requires video input)")
            image_to_video(args.image, args.seconds, anchor_loop)
            print(f">>> 2) Sync.so lipsync (announcer video + audio)")
            sync_lipsync_fn(anchor_loop, opener_audio, opener_raw)
        print(f">>> 3) normalizing opener to 1080x1920@30fps")
        normalize_opener(opener_raw, opener_norm)
        print(f">>> 3b) compositing title + per-segment subtitle + date badge")
        opener_with_caps = td / "opener_caps.mp4"
        apply_captions_to_opener(opener_norm, args.short, args.seconds, opener_with_caps)
        print(f">>> 4) trimming short to skip first {args.seconds}s")
        trim_short(args.short, args.seconds, trimmed)
        print(f">>> 5) concatenating opener + trimmed short")
        concat_clips(opener_with_caps, trimmed, final)

        if args.in_place:
            shutil.copy(final, args.short)
            print(f"✓ replaced in place: {args.short}")
        else:
            shutil.copy(final, out_path)
            print(f"✓ wrote: {out_path}")
        if args.keep_tmp:
            tmp_keep = args.short.parent / f"{args.short.stem}_anchor_tmp"
            shutil.copytree(td, tmp_keep, dirs_exist_ok=True)
            print(f"  tmp files copied to: {tmp_keep}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
