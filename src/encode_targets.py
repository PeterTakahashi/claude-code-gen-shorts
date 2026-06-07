"""Per-target encoding (M8).

Reads `project.yaml.output_targets[]` and re-encodes the chapter's master
scroll mp4 into each target. Skips targets whose output already exists.

Recognized aspect strings: "9:16", "16:9", "1:1", "4:5". The 1080×1920 source
is letterboxed/padded as needed (no content cropping by default).

Recognized kinds:
  - {kind: "video", aspect: "9:16", max_duration_s: 60}   # default
  - {kind: "static"}    # copies the chapter webtoon.png as the deliverable
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .project import Chapter, ProjectContext, load


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(args[:8])} …\n{r.stderr[-1500:]}")


def _ffprobe_duration(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def _aspect_filter(src_w: int, src_h: int, target_aspect: str) -> tuple[int, int, str]:
    """Compute target (w, h) and a filter string that fits source into target.

    Strategy: scale source to fit inside target preserving aspect, then pad the
    rest to black. Avoids cropping content.
    """
    aw, ah = (int(x) for x in target_aspect.split(":"))
    # Pick a base dimension. Use 1080 long edge.
    if aw <= ah:    # 9:16 etc.
        out_w = 1080
        out_h = int(out_w * ah / aw)
    else:           # 16:9 etc.
        out_h = 1080
        out_w = int(out_h * aw / ah)
    # Round to even (h264 friendly).
    out_w -= out_w % 2
    out_h -= out_h % 2

    # ffmpeg filter:  scale=w:h:force_original_aspect_ratio=decrease,pad=W:H:(W-iw)/2:(H-ih)/2
    flt = (
        f"scale=w={out_w}:h={out_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    return out_w, out_h, flt


def encode_target(
    chapter: Chapter,
    target: dict,
    *,
    force: bool = False,
) -> Path | None:
    name = target.get("name") or target.get("id")
    if not name:
        raise ValueError("output_target needs `name`")
    kind = target.get("kind", "video")

    if kind == "static":
        out = chapter.output_dir / f"{name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and not force:
            return out
        # Copy the chapter webtoon.png if it exists.
        src = chapter.webtoon_png
        if not src.exists():
            print(f"  ! skip {name}: source {src} missing")
            return None
        out.write_bytes(src.read_bytes())
        print(f"  ✓ {name}.png  ← {src}")
        return out

    if kind != "video":
        print(f"  ! unknown kind={kind!r} for target {name}; skipping")
        return None

    src = chapter.webtoon_scroll_mp4
    if not src.exists():
        print(f"  ! skip {name}: source {src} missing")
        return None

    aspect = target.get("aspect", "9:16")
    max_duration_s = target.get("max_duration_s")  # optional cap
    bitrate = target.get("video_bitrate", "4M")
    audio_bitrate = target.get("audio_bitrate", "192k")

    out = chapter.output_dir / f"{name}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not force:
        print(f"  ✓ already encoded: {name}.mp4")
        return out

    out_w, out_h, vf = _aspect_filter(1080, 1920, aspect)

    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if max_duration_s is not None:
        cmd += ["-t", f"{float(max_duration_s):.3f}"]
    cmd += [
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-b:v", bitrate, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        str(out),
    ]
    print(f"  → {name}.mp4  ({out_w}×{out_h}, max={max_duration_s}s)")
    _ffmpeg(cmd)
    print(f"    ✓ {out}  duration={_ffprobe_duration(out):.1f}s  size={out.stat().st_size//1024//1024} MB")
    return out


def encode_chapter_targets(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> list[Path]:
    targets = project.raw.get("output_targets") or []
    if not targets:
        print("  (no output_targets in project.yaml — skipping)")
        return []
    out: list[Path] = []
    for t in targets:
        try:
            r = encode_target(chapter, t, force=force)
            if r:
                out.append(r)
        except Exception as e:
            print(f"  ⚠ {t.get('name', '?')}: {e}")
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python -m src.encode_targets <project_id> <chapter_id> [--force]", file=sys.stderr)
        return 1
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    encode_chapter_targets(project, chapter, force="--force" in sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
