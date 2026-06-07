"""End-to-end orchestrator: novel.txt → scroll video, with human checkpoints.

  uv run python -m src.pipeline <project_id> [--chapter <chapter_id>] [--force]

Stages run in order; each is idempotent (skipped if its output already exists).
At human-review checkpoints the script prints clear instructions and exits with
code 0. Re-running the same command continues past the checkpoint once the
expected file/state is present.

Stage list:
  S0 validate project.yaml + input/novel.txt
  S1 split novel by chapter markers → work/chapters/<ch>/novel.txt
  S2 [LLM] characters.yaml — pause for review if newly created
  S3 4 character candidates per character via Gemini
  S4 [HUMAN] pick a candidate and copy → selected.png  (or set selected_candidate)
  S5 stylesheets via Gemini (turnaround + expressions)
  S6 [LLM, per chapter] scenes.json — pause for review if newly created
  S7 panels via Gemini (per chapter)
  S8 [HUMAN, per chapter] bubbles.json — pause for hand-authoring if missing
  S9 webtoon.png + panel_positions.json (per chapter)
  S10 multi-voice TTS (per chapter)
  S11 scroll_video → output/<ch>/webtoon_scroll.mp4 (per chapter)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass

from . import (
    audio_mixer,
    character_designer,
    codex_review,
    encode_targets,
    llm,
    narrate,
    novel_loader,
    render_panels,
    style_sheet,
    synth_bgm,
    synth_sfx,
    video_assembler,
    voice_install,
    voice_verify,
)
from .project import Chapter, ProjectContext, load


@dataclass
class Checkpoint(Exception):
    title: str
    instructions: str

    def __str__(self) -> str:  # noqa: D401
        return f"{self.title}\n{self.instructions}"


# ---------- stages ----------

def stage_0_validate(project: ProjectContext) -> None:
    if not project.input_novel.exists():
        raise Checkpoint(
            title=f"S0: missing {project.input_novel}",
            instructions=(
                f"Drop the novel text at:\n  {project.input_novel}\n"
                "and re-run the pipeline."
            ),
        )
    print(f"  ✓ {project.input_novel}  ({project.input_novel.stat().st_size} bytes)")


def stage_1_split(project: ProjectContext, force: bool) -> None:
    novel_loader.split_chapters(project, force=force)


def stage_2_characters(project: ProjectContext) -> None:
    if project.characters_yaml.exists():
        print(f"  ✓ {project.characters_yaml}  ({len(project.characters)} characters)")
        return
    print(f"  → characters.yaml missing; invoking claude -p to extract from {project.input_novel.name} …")
    llm.extract_characters(project)
    raise Checkpoint(
        title="S2: characters.yaml just generated — review before continuing",
        instructions=(
            f"Review and edit:\n  {project.characters_yaml}\n"
            "Then re-run the pipeline.\n"
            "Things to check:\n"
            "  - every important character is listed\n"
            "  - description_en is appearance-only (no plot/personality)\n"
            "  - voice assignments make sense for the cast\n"
        ),
    )


def _needs_design(c) -> bool:
    """A character needs candidate/stylesheet generation if it has expression specs.

    Characters without `expressions:` are description-only — they appear in
    panels via prompt injection but don't get an identity-locking stylesheet.
    """
    return bool(c.expressions)


def stage_3_candidates(project: ProjectContext) -> None:
    candidates = [c for c in project.characters if _needs_design(c)]
    targets = [c for c in candidates if not c.candidates_dir(project.project_dir).is_dir()
               or len(list(c.candidates_dir(project.project_dir).glob("candidate_*.png"))) < 4]
    if not targets:
        print(f"  ✓ candidates present for all {len(candidates)} designed characters")
        return
    for c in targets:
        print(f"  → generating 4 candidates for {c.id}")
        character_designer.generate_candidates(project, c)


def stage_4_select(project: ProjectContext) -> None:
    needs_pick: list[str] = []
    for c in project.characters:
        if not _needs_design(c):
            continue
        sel = c.selected_png(project.project_dir)
        if sel.exists():
            continue
        # Try to auto-copy if selected_candidate is set
        if c.selected_candidate is not None:
            src = c.candidates_dir(project.project_dir) / f"candidate_{c.selected_candidate}.png"
            if src.exists():
                shutil.copyfile(src, sel)
                print(f"  ✓ {c.id}: candidate_{c.selected_candidate}.png → selected.png")
                continue
        needs_pick.append(c.id)

    if needs_pick:
        details = "\n".join(
            f"  - {cid}: pick from {project.character(cid).candidates_dir(project.project_dir)}"
            for cid in needs_pick
        )
        raise Checkpoint(
            title=f"S4: {len(needs_pick)} character(s) need a design selection",
            instructions=(
                f"For each character below, open the 4 candidate PNGs and pick one. Then either:\n"
                f"  (a) edit characters.yaml and set `selected_candidate: <N>` (1..4), or\n"
                f"  (b) copy your pick: cp .../candidates/candidate_<N>.png .../selected.png\n\n"
                f"{details}\n"
            ),
        )
    designed = [c for c in project.characters if _needs_design(c)]
    print(f"  ✓ selected.png present for all {len(designed)} designed characters")


def stage_voices_check(project: ProjectContext) -> None:
    """Verify that every voice_style_id referenced by the project is installed
    on the Aivis engine. Raise Checkpoint with install instructions if not.
    """
    try:
        result = voice_install.check(project)
    except RuntimeError as e:
        # Aivis unreachable — soft-fail with instructions, allow pipeline to continue
        # (TTS stage will hard-fail later if Aivis is still down then).
        print(f"  ⚠ {e}")
        print("  ↳ pipeline will continue, but S10 (TTS) will fail until Aivis is up.")
        return
    if result.ok:
        print(f"  ✓ {len(result.required)} voice style(s) ready on Aivis")
        return
    voice_install.report(project, result)
    raise Checkpoint(
        title=f"S4: {len(result.missing)} voice style(s) missing on Aivis engine",
        instructions=(
            "Install the missing styles before continuing:\n"
            "  - Open Aivis app, or\n"
            "  - Download .aivmx from https://hub.aivis-project.com and POST to "
            "http://127.0.0.1:10101/aivm_models/install\n"
            "Re-run the pipeline once installed.\n"
            "(Or edit characters.yaml to point voice_style_id at a style that IS installed.)"
        ),
    )


def stage_5_stylesheets(project: ProjectContext) -> None:
    todo = [c for c in project.characters
            if _needs_design(c)
            and c.selected_png(project.project_dir).exists()
            and (not c.stylesheet_turnaround(project.project_dir).exists()
                 or not c.stylesheet_expression(project.project_dir).exists())]
    if not todo:
        print("  ✓ stylesheets present for all selected characters")
        return
    for c in todo:
        try:
            style_sheet.generate_stylesheet(project, c)
        except RuntimeError as e:
            print(f"  ! skip {c.id}: {e}")


def stage_6_scenes(project: ProjectContext, chapter: Chapter) -> None:
    if chapter.scenes_json.exists():
        return
    print(f"  → scenes.json missing for {chapter.id}; invoking claude -p …")
    llm.decompose_scenes(project, chapter.id)
    raise Checkpoint(
        title=f"S6: scenes.json just generated for {chapter.id} — review before continuing",
        instructions=(
            f"Review and edit:\n  {chapter.scenes_json}\n"
            "Then re-run the pipeline.\n"
            "Things to check:\n"
            "  - all narrative beats are covered\n"
            "  - shot_type / aspect_ratio variety\n"
            "  - characters_in_panel ids match characters.yaml\n"
        ),
    )


def stage_7_panels(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    render_panels.render_chapter(project, chapter, force=force)


def stage_8_bubbles(project: ProjectContext, chapter: Chapter) -> None:
    """Author bubbles.json by feeding rendered panels to claude -p (vision)."""
    if chapter.bubbles_json.exists():
        return
    print(f"  → bubbles.json missing for {chapter.id}; invoking claude -p with panel images …")
    llm.author_bubbles(project, chapter.id)
    raise Checkpoint(
        title=f"S8: bubbles.json just generated for {chapter.id} — review before continuing",
        instructions=(
            f"Review and edit:\n  {chapter.bubbles_json}\n"
            "Then re-run the pipeline.\n"
            "Things to check:\n"
            "  - bubble x_pct/y_pct don't cover faces (open the bubbled preview to verify)\n"
            "  - speaker ids match characters.yaml\n"
            "  - SFX prompts match what's actually happening in the panel\n"
            "  - linked_sfx_id pairs match scenes.json in_image_text[] entries\n"
            "  - scene_bgm prompts give a coherent atmosphere arc across scenes\n"
        ),
    )


def stage_sfx(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    """ElevenLabs SFX per panel. Skipped if bubbles.json has no sfx[] entries."""
    synth_sfx.synthesize_chapter_sfx(project, chapter, force=force)


def stage_bgm(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    """ElevenLabs BGM per scene with ffmpeg loop+fade. Skipped if no scene_bgm[]."""
    synth_bgm.synthesize_chapter_bgm(project, chapter, force=force)


def stage_10_audio(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    narrate.narrate_chapter(project, chapter, force=force)


def stage_audio_mix(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    """M4: per-panel mix (voice + sfx) → chapter master with BGM + ducking."""
    audio_mixer.build_chapter_master(project, chapter, force=force)


def stage_assemble_video(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    """16:9 still-cut chapter video + master audio + burned subtitles."""
    if chapter.master_mp4.exists() and chapter.subtitles_srt.exists() and not force:
        print(f"  ✓ {chapter.master_mp4}")
        return
    video_assembler.build_chapter_video(project, chapter, force=force)


def stage_voice_verify(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    """M5 layer 3: Whisper-verify Aivis voice. Optional — controlled by project.yaml voice.verify."""
    if not (project.raw.get("voice", {}) or {}).get("verify", False):
        print("  (voice.verify=false in project.yaml; skipping Whisper verification)")
        return
    findings = voice_verify.verify_chapter(project, chapter, force=force)
    if findings:
        raise Checkpoint(
            title=f"S13b: {len(findings)} voice clip(s) below similarity threshold",
            instructions=(
                f"Review {chapter.work_dir / 'voice_review.md'}\n"
                f"Merge accepted lexicon entries into {project.lexicon_yaml}, then re-run with --force\n"
                "to re-synthesize the flagged panels."
            ),
        )


def stage_codex_review(project: ProjectContext, chapter: Chapter, *, after_bubbles: bool) -> None:
    """M6: optional Codex review of scenes/bubbles. Skips if disabled."""
    review_cfg = project.raw.get("review", {}) or {}
    if not review_cfg.get("codex_enabled", False):
        return
    try:
        codex_review.review_chapter(project, chapter)
    except Exception as e:
        print(f"  ⚠ codex review skipped: {e}")


def stage_encode_targets(project: ProjectContext, chapter: Chapter, force: bool) -> None:
    """M8: per-target encoding (TikTok 9:16, YouTube 16:9, etc.)."""
    encode_targets.encode_chapter_targets(project, chapter, force=force)


# ---------- driver ----------

def run(project_id: str, chapter_filter: str | None, force: bool) -> int:
    project = load(project_id)
    print(f"=== Project: {project.title_ja} ({project.id}) ===\n")

    pre_chapter_stages = [
        ("S0  validate inputs", stage_0_validate, lambda: stage_0_validate(project)),
        ("S1  split novel into chapters", None, lambda: stage_1_split(project, force=force)),
        ("S2  extract characters.yaml", None, lambda: stage_2_characters(project)),
        ("S2.5 verify Aivis voice models", None, lambda: stage_voices_check(project)),
        ("S3  generate character candidates", None, lambda: stage_3_candidates(project)),
        ("S4  select character designs", None, lambda: stage_4_select(project)),
        ("S5  generate stylesheets", None, lambda: stage_5_stylesheets(project)),
    ]

    try:
        for label, _, fn in pre_chapter_stages:
            print(f"--- {label} ---")
            fn()
            print()

        chapters = [c for c in project.chapters if not chapter_filter or c.id == chapter_filter]
        for chapter in chapters:
            print(f"\n=== Chapter: {chapter.title} ({chapter.id}) ===\n")
            for label, fn in [
                (f"S6  decompose scenes ({chapter.id})",   lambda c=chapter: stage_6_scenes(project, c)),
                (f"S6r codex review scenes ({chapter.id})", lambda c=chapter: stage_codex_review(project, c, after_bubbles=False)),
                (f"S7  render panels ({chapter.id})",      lambda c=chapter: stage_7_panels(project, c, force=force)),
                (f"S8  author bubbles ({chapter.id})",     lambda c=chapter: stage_8_bubbles(project, c)),
                (f"S8r codex review bubbles ({chapter.id})", lambda c=chapter: stage_codex_review(project, c, after_bubbles=True)),
                (f"S10 narrate audio ({chapter.id})",      lambda c=chapter: stage_10_audio(project, c, force=force)),
                (f"S10b voice verify ({chapter.id})",      lambda c=chapter: stage_voice_verify(project, c, force=force)),
                (f"S10c sfx ({chapter.id})",               lambda c=chapter: stage_sfx(project, c, force=force)),
                (f"S10d bgm ({chapter.id})",               lambda c=chapter: stage_bgm(project, c, force=force)),
                (f"S12 audio master ({chapter.id})",       lambda c=chapter: stage_audio_mix(project, c, force=force)),
                (f"S13 assemble video ({chapter.id})",     lambda c=chapter: stage_assemble_video(project, c, force=force)),
                (f"S14 encode targets ({chapter.id})",     lambda c=chapter: stage_encode_targets(project, c, force=force)),
            ]:
                print(f"--- {label} ---")
                fn()
                print()

    except Checkpoint as cp:
        print("\n" + "=" * 60)
        print(f"⏸  PAUSED: {cp.title}")
        print("=" * 60)
        print(cp.instructions)
        return 0

    print("\n" + "=" * 60)
    print("✅ All stages complete.")
    print("=" * 60)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="src.pipeline")
    ap.add_argument("project_id")
    ap.add_argument("--chapter", default=None, help="run only this chapter id")
    ap.add_argument("--force", action="store_true", help="regenerate even when outputs exist")
    args = ap.parse_args()
    return run(args.project_id, args.chapter, args.force)


if __name__ == "__main__":
    sys.exit(main())
