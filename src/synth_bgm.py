"""Generate per-scene BGM (ambience) from a chapter's bubbles.json.

ElevenLabs SFX max duration is ~22s. For BGM we:
  1. Generate a base ambience clip (~20s) via /v1/sound-generation
  2. Loop with `ffmpeg -stream_loop` to the scene's required total seconds
  3. Apply afade in (0.8s) + afade out (1.2s) at the boundaries

Required scene duration is computed from the per-panel voice durations:
  scene_duration = Σ (voice_<pid>.mp3 duration) + (n_panels - 1) * transition_s

bubbles.json shape (additive):
  scene_bgm: [
    { "scene_id": "scene_01",
      "elevenlabs_prompt": "quiet melancholic ambient drone",
      "volume_db": -18,           # used by audio mixer (M4)
      "loop": true,
      "fade_in_s": 0.8,
      "fade_out_s": 1.2,
      "extra_tail_s": 1.5,        # how much BGM to extend beyond last voice
      "prompt_influence": 0.3 }

Output: <chapter.audio_bgm_dir>/<scene_id>.wav (wav for lossless looping)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .elevenlabs import SFX_MAX_DURATION_S, generate_sound_effect
from .project import Chapter, ProjectContext, load


# Default BGM base ambience length — picks a clip to loop from.
BASE_AMBIENCE_S = 20.0
DEFAULT_FADE_IN_S = 0.8
DEFAULT_FADE_OUT_S = 1.2
DEFAULT_EXTRA_TAIL_S = 1.5


def probe_duration_s(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def scene_voice_duration(chapter: Chapter, scene_panels: list[dict], transition_s: float = 0.5) -> float:
    """Sum the voice durations for panels in a scene; add transition_s between panels."""
    total = 0.0
    n_with_audio = 0
    for p in scene_panels:
        wav = chapter.audio_dir / f"{p['panel_id']}.mp3"
        if wav.exists():
            total += probe_duration_s(wav)
            n_with_audio += 1
    if n_with_audio > 1:
        total += transition_s * (n_with_audio - 1)
    return total


def loop_with_fades(
    base: Path, target_duration_s: float, fade_in_s: float, fade_out_s: float, out_path: Path
) -> Path:
    """ffmpeg: loop `base` to target_duration_s, apply fade in/out, write wav."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fo_start = max(0.0, target_duration_s - fade_out_s)
    af = f"afade=t=in:d={fade_in_s},afade=t=out:st={fo_start:.3f}:d={fade_out_s}"
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(base),
        "-t", f"{target_duration_s:.3f}",
        "-af", af,
        "-ar", "44100", "-ac", "2",
        "-c:a", "pcm_s16le",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg loop+fade failed:\n{r.stderr[-1500:]}")
    return out_path


def synthesize_chapter_bgm(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> int:
    if not chapter.bubbles_json.exists():
        raise FileNotFoundError(f"missing {chapter.bubbles_json}")
    if not chapter.scenes_json.exists():
        raise FileNotFoundError(f"missing {chapter.scenes_json}")

    bubbles_cfg = json.loads(chapter.bubbles_json.read_text(encoding="utf-8"))
    scenes_cfg = json.loads(chapter.scenes_json.read_text(encoding="utf-8"))
    scene_panels: dict[str, list[dict]] = {s["id"]: s["panels"] for s in scenes_cfg.get("scenes", [])}

    bgm_entries = bubbles_cfg.get("scene_bgm") or []
    if not bgm_entries:
        print("  (no scene_bgm[] entries in bubbles.json — skipping)")
        return 0

    chapter.audio_bgm_dir.mkdir(parents=True, exist_ok=True)
    n_done = 0
    for entry in bgm_entries:
        scene_id = entry["scene_id"]
        panels = scene_panels.get(scene_id)
        if not panels:
            print(f"  ⚠ {scene_id}: not in scenes.json, skipping BGM")
            continue

        out_path = chapter.audio_bgm_dir / f"{scene_id}.wav"
        if out_path.exists() and not force:
            print(f"  skip existing: {scene_id}")
            continue

        prompt = entry.get("elevenlabs_prompt") or entry.get("prompt")
        if not prompt:
            print(f"  ⚠ {scene_id}: missing elevenlabs_prompt, skipping")
            continue

        fade_in = float(entry.get("fade_in_s", DEFAULT_FADE_IN_S))
        fade_out = float(entry.get("fade_out_s", DEFAULT_FADE_OUT_S))
        extra_tail = float(entry.get("extra_tail_s", DEFAULT_EXTRA_TAIL_S))

        scene_voice_total = scene_voice_duration(chapter, panels)
        target_total = max(scene_voice_total + extra_tail, 4.0)  # at least 4s of BGM
        print(f"  [{scene_id}] target={target_total:.1f}s  prompt={prompt[:60]!r}")

        with tempfile.TemporaryDirectory() as td:
            base_path = Path(td) / f"{scene_id}_base.mp3"
            base_dur = min(BASE_AMBIENCE_S, SFX_MAX_DURATION_S)
            generate_sound_effect(
                prompt,
                base_path,
                duration_seconds=base_dur,
                prompt_influence=float(entry.get("prompt_influence", 0.3)),
            )
            actual_base = probe_duration_s(base_path)
            print(f"    base={actual_base:.1f}s, looping → {target_total:.1f}s")
            loop_with_fades(base_path, target_total, fade_in, fade_out, out_path)
            n_done += 1

    print(f"\n  ✅ bgm: generated={n_done}, total={len(bgm_entries)}")
    return n_done


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.synth_bgm <project_id> <chapter_id> [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    synthesize_chapter_bgm(project, chapter, force="--force" in sys.argv)


if __name__ == "__main__":
    main()
