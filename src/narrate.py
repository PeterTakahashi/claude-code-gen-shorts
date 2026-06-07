"""Generate per-panel multi-voice narration MP3s from a chapter's bubbles.json.

Each bubble within a panel is synthesized via Aivis with the speaker's
voice_style_id (from characters.yaml). narration_box / monologue_box use the
project narrator voice. Bubble audios are concatenated into one MP3 per panel.

Side effect — `_subtitles.json` is written under the chapter's audio dir:
  { panel_id: { duration_s, bubbles: [{idx, speaker, text, start_s, end_s}] } }
This becomes the source for video_assembler's SRT generation.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .narrator_helpers import synthesize
from .project import Chapter, ProjectContext, load
from .subtitle_split import DEFAULT_MAX_CHARS, split_for_display, split_for_tts


def _bubble_speaker(bubble: dict) -> str:
    btype = bubble.get("type", "")
    if btype in ("narration_box", "monologue_box"):
        return "narrator"
    return bubble.get("speaker") or "narrator"


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def synthesize_panel(
    project: ProjectContext,
    bubbles: list[dict],
    out_path: Path,
) -> tuple[Path, list[dict]]:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not bubbles:
        # 1.2s silence so panels with no text still hold briefly in the video.
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "anullsrc=channel_layout=mono:sample_rate=44100",
             "-t", "1.2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)],
            check=True, capture_output=True,
        )
        return out_path, []

    # Layer 1 of reading control: pre-replace known words with their kana
    # readings. Falls back to a no-op if lexicon.yaml is absent/empty.
    lexicon = project.load_lexicon()

    panel_subs: list[dict] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_p = Path(tmpdir)
        segs: list[Path] = []
        cumulative = 0.0
        seg_index = 0
        for bub_idx, b in enumerate(bubbles):
            speaker = _bubble_speaker(b)
            style_id, speed, pitch, intonation, _instructions = project.voice_for(speaker)
            raw_text = (b.get("text") or "").strip()
            if not raw_text:
                continue
            if style_id is None:
                raise RuntimeError(
                    f"no voice_style_id resolved for speaker={speaker!r} "
                    "(set narrator.voice_style_id in project.yaml or character.voice_style_id)"
                )
            override = (b.get("reading_override") or "").strip()

            # Sentence-level TTS chunking — one synthesize() call per full
            # Japanese sentence so Aivis gives it natural prosody. Never split
            # mid-sentence at `、` (that produces choppy tone jumps).
            tts_chunks = split_for_tts(raw_text)
            if not tts_chunks:
                continue

            print(f"  [bubble {bub_idx+1}/{len(bubbles)}] {speaker} (style={style_id}) — {len(tts_chunks)} sentence(s)")

            for tts_text in tts_chunks:
                text_for_tts = override or lexicon.apply(tts_text)
                seg_path = tmpdir_p / f"seg_{seg_index:02d}_{speaker}.mp3"
                print(f"    [TTS {seg_index+1}] {len(tts_text)} chars: {tts_text[:40]}…")
                synthesize(
                    text_for_tts, seg_path,
                    voice=style_id, speed=speed, pitch=pitch, intonation=intonation,
                )
                seg_dur = _ffprobe_duration(seg_path)

                # Now allocate the audio duration across display pieces
                # proportionally to character count — keeps subtitle ≤35 chars
                # while preserving the whole-sentence TTS prosody.
                display_pieces = split_for_display(tts_text, max_chars=DEFAULT_MAX_CHARS)
                total_chars = sum(len(p) for p in display_pieces) or 1
                piece_t = cumulative
                for piece in display_pieces:
                    piece_dur = seg_dur * (len(piece) / total_chars)
                    panel_subs.append({
                        "idx": seg_index,
                        "speaker": speaker,
                        "text": piece,
                        "start_s": piece_t,
                        "end_s": piece_t + piece_dur,
                    })
                    piece_t += piece_dur

                cumulative += seg_dur
                segs.append(seg_path)
                seg_index += 1

        if not segs:
            raise RuntimeError("no segments generated")

        concat_list = tmpdir_p / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in segs),
            encoding="utf-8",
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)],
            check=True, capture_output=True,
        )
    return out_path, panel_subs


def narrate_chapter(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> Path:
    if not chapter.bubbles_json.exists():
        raise FileNotFoundError(f"missing {chapter.bubbles_json}")
    cfg = json.loads(chapter.bubbles_json.read_text(encoding="utf-8"))
    chapter.audio_dir.mkdir(parents=True, exist_ok=True)

    subs_path = chapter.audio_dir / "_subtitles.json"
    subs_data: dict = {}
    if subs_path.exists():
        try:
            subs_data = json.loads(subs_path.read_text(encoding="utf-8"))
        except Exception:
            subs_data = {}

    panels = cfg["panels"]
    for i, p in enumerate(panels):
        pid = p["panel_id"]
        out = chapter.audio_dir / f"{pid}.mp3"
        bubbles = p.get("bubbles", [])

        if out.exists() and not force and pid in subs_data:
            print(f"skip existing: {pid}")
            continue

        print(f"[{i+1}/{len(panels)}] {pid}  ({len(bubbles)} bubbles)")
        _, panel_subs = synthesize_panel(project, bubbles, out)
        # Always (re)record entry so SRT regen stays in sync with mp3 on disk
        subs_data[pid] = {
            "duration_s": _ffprobe_duration(out),
            "bubbles": panel_subs,
        }
        subs_path.write_text(
            json.dumps(subs_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"\n✅ multi-voice narration ready under {chapter.audio_dir}/")
    print(f"   subtitle timing → {subs_path.name}")
    return chapter.audio_dir


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.narrate <project_id> <chapter_id> [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    narrate_chapter(project, chapter, force="--force" in sys.argv)


if __name__ == "__main__":
    main()
