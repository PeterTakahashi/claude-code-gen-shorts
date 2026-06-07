"""3-track audio mixer: voice + SFX + BGM with sidechain ducking.

Two-step build:
  1. `build_panel_mix(...)` — per panel: voice + same-panel sfx → audio/mix/<pid>.wav
  2. `build_chapter_master(...)` — concat panel mixes with transitions, overlay
     scene BGMs, sidechain-duck BGM against voice → audio/mix/chapter_master.wav

Then `apply_master_to_video(...)` muxes the master audio onto the rendered
scroll mp4 (replacing the per-panel voice audio scroll_video bakes in).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .project import Chapter, ProjectContext, load


TRANSITION_S = 0.0  # instant cuts in the new video_assembler flow (no scroll transitions)


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


# ---------- per-panel mix ----------

def build_panel_mix(chapter: Chapter, panel_id: str, sfx_entries: list[dict] | None, *, force: bool = False) -> Path | None:
    voice = chapter.audio_dir / f"{panel_id}.mp3"
    if not voice.exists():
        return None
    out = chapter.audio_mix_dir / f"{panel_id}.wav"
    if out.exists() and not force:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)

    # Filter sfx entries to those whose file actually exists.
    valid_sfx: list[tuple[Path, dict]] = []
    for sfx in sfx_entries or []:
        sfx_path = chapter.audio_sfx_dir / f"{panel_id}_{sfx.get('id')}.mp3"
        if sfx_path.exists():
            valid_sfx.append((sfx_path, sfx))

    if not valid_sfx:
        # Just transcode voice to wav for consistent format.
        _ffmpeg(["ffmpeg", "-y", "-i", str(voice),
                 "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out)])
        return out

    inputs: list[str] = ["-i", str(voice)]
    for sp, _ in valid_sfx:
        inputs += ["-i", str(sp)]

    filter_parts: list[str] = []
    sfx_labels: list[str] = []
    for i, (_, sfx) in enumerate(valid_sfx):
        delay_ms = max(0, int(float(sfx.get("start_offset_s", 0.0)) * 1000))
        vol_db = float(sfx.get("volume_db", -6.0))
        filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms},volume={vol_db}dB[s{i}]")
        sfx_labels.append(f"[s{i}]")

    if len(sfx_labels) == 1:
        filter_parts.append(f"[0:a]{sfx_labels[0]}amix=inputs=2:normalize=0:weights='1.5 1.0':duration=longest[out]")
    else:
        filter_parts.append(f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:normalize=0:duration=longest[sfx]")
        filter_parts.append("[0:a][sfx]amix=inputs=2:normalize=0:weights='1.5 1.0':duration=longest[out]")

    _ffmpeg(["ffmpeg", "-y", *inputs,
             "-filter_complex", ";".join(filter_parts),
             "-map", "[out]",
             "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
             str(out)])
    return out


# ---------- chapter master ----------

def _silence_wav(duration_s: float, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["ffmpeg", "-y",
             "-f", "lavfi", "-t", f"{duration_s:.4f}",
             "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
             "-c:a", "pcm_s16le", str(out_path)])
    return out_path


def _concat_with_silence(segments: list[Path], silence_after: list[float], out: Path) -> Path:
    """Concat WAV segments with per-segment trailing silence."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        list_path = td / "concat.txt"
        # Pre-build silence wavs (cache by duration)
        silence_cache: dict[float, Path] = {}
        lines: list[str] = []
        for i, seg in enumerate(segments):
            lines.append(f"file '{seg.resolve()}'")
            gap = silence_after[i] if i < len(silence_after) else 0.0
            if gap > 0:
                key = round(gap, 3)
                if key not in silence_cache:
                    silence_cache[key] = _silence_wav(gap, td / f"silence_{int(gap*1000)}.wav")
                lines.append(f"file '{silence_cache[key].resolve()}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")
        _ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
                 "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(out)])
    return out


def build_chapter_master(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> Path:
    """Build the final chapter audio: voice+sfx + scene BGM (sidechain-ducked).

    Layout:
      [voice/sfx track]   <━ concat of audio/mix/<pid>.wav with TRANSITION_S silence between
      [bgm track]         <━ silence base, scene_bgm overlays at scene start times
      mix:                voice (1.5×) + bgm (sidechain-ducked, 0.6×)
    """
    out = chapter.audio_master_wav
    if out.exists() and not force:
        print(f"  ✓ already built: {out}")
        return out
    out.parent.mkdir(parents=True, exist_ok=True)

    if not chapter.scenes_json.exists():
        raise FileNotFoundError(f"missing {chapter.scenes_json}")
    scenes_cfg = json.loads(chapter.scenes_json.read_text(encoding="utf-8"))
    scenes = scenes_cfg["scenes"]

    bubbles_cfg: dict = {}
    if chapter.bubbles_json.exists():
        bubbles_cfg = json.loads(chapter.bubbles_json.read_text(encoding="utf-8"))
    sfx_by_panel: dict[str, list[dict]] = {p["panel_id"]: p.get("sfx") or [] for p in bubbles_cfg.get("panels", [])}
    scene_bgm_entries = bubbles_cfg.get("scene_bgm") or []
    bgm_by_scene: dict[str, dict] = {b["scene_id"]: b for b in scene_bgm_entries}

    # 1) Build per-panel mixes (idempotent), gather paths and durations.
    segments: list[Path] = []
    silence_after: list[float] = []
    panel_starts: dict[str, float] = {}     # panel_id → start s in master timeline
    scene_starts: dict[str, float] = {}     # scene_id → start s in master timeline
    cursor = 0.0

    for s_idx, scene in enumerate(scenes):
        scene_starts[scene["id"]] = cursor
        panels = scene["panels"]
        for p_idx, panel in enumerate(panels):
            pid = panel["panel_id"]
            mix_path = build_panel_mix(chapter, pid, sfx_by_panel.get(pid, []), force=force)
            if mix_path is None:
                continue
            duration = _ffprobe_duration(mix_path)
            panel_starts[pid] = cursor
            segments.append(mix_path)
            cursor += duration
            # silence between panels — TRANSITION_S between panels in same scene
            # AND between scenes (matches scroll_video transition pattern).
            is_last_in_chapter = (s_idx == len(scenes) - 1) and (p_idx == len(panels) - 1)
            silence_after.append(0.0 if is_last_in_chapter else TRANSITION_S)
            if not is_last_in_chapter:
                cursor += TRANSITION_S

    if not segments:
        raise RuntimeError(f"no per-panel mixes available under {chapter.audio_mix_dir}")

    total_duration = cursor

    # 2) Build voice+sfx concat track.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        voice_track = _concat_with_silence(segments, silence_after, td / "voice_sfx.wav")
        actual_voice_dur = _ffprobe_duration(voice_track)
        print(f"  voice+sfx track: {actual_voice_dur:.2f}s ({len(segments)} segments)")

        # 3) Build BGM overlays.
        bgm_inputs: list[Path] = []
        bgm_offsets_ms: list[int] = []
        bgm_volumes_db: list[float] = []
        for scene in scenes:
            entry = bgm_by_scene.get(scene["id"])
            if not entry:
                continue
            bgm_path = chapter.audio_bgm_dir / f"{scene['id']}.wav"
            if not bgm_path.exists():
                print(f"  ⚠ {scene['id']}: scene_bgm declared but {bgm_path} missing — skip")
                continue
            bgm_inputs.append(bgm_path)
            bgm_offsets_ms.append(max(0, int(scene_starts[scene["id"]] * 1000)))
            bgm_volumes_db.append(float(entry.get("volume_db", -18.0)))

        if not bgm_inputs:
            # No BGM — voice+sfx track IS the master.
            _ffmpeg(["ffmpeg", "-y", "-i", str(voice_track),
                     "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(out)])
            print(f"  (no BGM) → {out}  duration={actual_voice_dur:.2f}s")
            return out

        # 4) Mix voice+sfx with BGM, sidechain-duck BGM against voice.
        inputs: list[str] = ["-i", str(voice_track)]
        for bp in bgm_inputs:
            inputs += ["-i", str(bp)]

        filter_parts: list[str] = []
        bgm_labels: list[str] = []
        for i, (offset_ms, vol_db) in enumerate(zip(bgm_offsets_ms, bgm_volumes_db)):
            filter_parts.append(f"[{i+1}:a]adelay={offset_ms}|{offset_ms},volume={vol_db}dB[bg{i}]")
            bgm_labels.append(f"[bg{i}]")

        if len(bgm_labels) == 1:
            filter_parts.append(f"{bgm_labels[0]}apad=whole_dur={total_duration:.4f}[bgm]")
        else:
            filter_parts.append(f"{''.join(bgm_labels)}amix=inputs={len(bgm_labels)}:normalize=0:duration=longest[bgm_raw]")
            filter_parts.append(f"[bgm_raw]apad=whole_dur={total_duration:.4f}[bgm]")

        # Sidechain ducking: drop bgm volume when voice is loud, but keep BGM
        # clearly audible underneath. Gentler than the original tuning so the
        # ambience reads through narration rather than disappearing.
        filter_parts.append(
            "[bgm][0:a]sidechaincompress=threshold=0.1:ratio=4:attack=10:release=400:makeup=2[bgm_ducked]"
        )
        filter_parts.append(
            "[0:a][bgm_ducked]amix=inputs=2:normalize=0:weights='1.4 1.0':duration=longest[out]"
        )

        _ffmpeg(["ffmpeg", "-y", *inputs,
                 "-filter_complex", ";".join(filter_parts),
                 "-map", "[out]",
                 "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
                 str(out)])

    actual_master_dur = _ffprobe_duration(out)
    print(f"  ✓ chapter_master.wav  duration={actual_master_dur:.2f}s  bgm_scenes={len(bgm_inputs)}")
    return out


# ---------- video overlay ----------

def apply_master_to_video(chapter: Chapter, *, force: bool = False) -> Path | None:
    """Replace the audio track of `webtoon_scroll.mp4` with the chapter master."""
    video = chapter.webtoon_scroll_mp4
    master = chapter.audio_master_wav
    if not video.exists() or not master.exists():
        return None

    backup = video.with_suffix(".prevoice.mp4")
    if backup.exists() and not force:
        # Already overlaid in a prior run.
        return video

    if not backup.exists():
        # First overlay — preserve original (voice-only) version.
        video.rename(backup)

    _ffmpeg([
        "ffmpeg", "-y",
        "-i", str(backup),
        "-i", str(master),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest",
        str(video),
    ])
    return video


# ---------- CLI ----------

def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.audio_mixer <project_id> <chapter_id> [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    force = "--force" in sys.argv
    build_chapter_master(project, chapter, force=force)
    # `apply_master_to_video` is retained for legacy users overlaying onto an
    # already-rendered scroll mp4, but the new flow has video_assembler mux the
    # master audio directly during assembly — no separate overlay needed.


if __name__ == "__main__":
    main()
