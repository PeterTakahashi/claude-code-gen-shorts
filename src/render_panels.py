"""Render any non-reused panels in a chapter's scenes.json via Gemini.

Idempotent: skips a panel if `<chapter_dir>/panels/<scene_id>/<pid>_best.png`
already exists, unless `--force` is set or the file is the reuse_from target.

Stylesheet refs (turnaround + expressions + selected.png) and the previous
panel are attached as Gemini reference images for identity + continuity.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .image_generator import generate_image, generate_images_batch
from .project import Chapter, ProjectContext, load


TREATMENT_HINTS: dict[str, str] = {
    "normal": "",
    "symbolic_dark": (
        "treatment: strongly symbolic, deep-shadow monochrome, heavy black negative space, "
        "single accent light source, minimalist composition, intense emotional focus"
    ),
    "imagined_surreal": (
        "treatment: this panel depicts the character's imagination — unreal and dreamlike; "
        "render with ghostly translucent overlays, soft edge bleeding into screentone darkness, "
        "a slightly surreal atmosphere distinct from real-world scenes"
    ),
    "photograph": (
        "treatment: rendered as an aged sepia-tinted family photograph within the panel — "
        "subtle paper texture, soft vignette, slightly washed tones, a faint worn edge"
    ),
    # Color overrides — used when the project default is color but a particular
    # panel should be rendered monochrome for narrative reasons.
    "monochrome": (
        "treatment: render in pure monochrome (black, white, gray screentone) ONLY — "
        "completely ignore any color-style directive above; this panel is a deliberate "
        "monochrome beat within an otherwise color webtoon"
    ),
    "flashback_monochrome": (
        "treatment: this panel is a memory/flashback rendered in soft sepia-toned monochrome — "
        "warm faded grays and cream tones, slightly washed-out, vignetted edges to signal "
        "we are looking into the past; ignore any color-style directive above"
    ),
    "dream_desaturated": (
        "treatment: this panel is a dream/imagined sequence rendered with heavily desaturated "
        "color (almost monochrome but with one or two accent hues), ethereal glow, soft "
        "edge dissolve into white"
    ),
}

# Treatments that imply a monochrome/desaturated override of the project's
# default style.description. When set, render_panels replaces the style line
# with a treatment-appropriate one to avoid color/monochrome contradictions.
_MONO_OVERRIDE_TREATMENTS: set[str] = {
    "symbolic_dark",
    "monochrome",
    "flashback_monochrome",
    "photograph",
}

_MONO_STYLE_DESCRIPTIONS: dict[str, str] = {
    "symbolic_dark": "high-contrast monochrome webtoon manga, heavy black ink, screentone shading, no color",
    "monochrome": "monochrome black-and-white webtoon manga, clean inked linework, screentone shading, no color",
    "flashback_monochrome": "warm sepia-toned monochrome webtoon manga, vintage paper texture, no full color",
    "photograph": "aged sepia photograph aesthetic, period-accurate film grain, no modern color",
}


_POSITION_PHRASES = {
    "upper-left": "in the upper-left of the frame",
    "upper-right": "in the upper-right of the frame",
    "lower-left": "in the lower-left of the frame",
    "lower-right": "in the lower-right of the frame",
    "background-left": "drifting in the background on the left",
    "background-right": "drifting in the background on the right",
    "center": "across the center of the frame",
    "top": "across the top of the frame",
    "bottom": "across the bottom of the frame",
}


def _format_in_image_text(items: list[dict]) -> str:
    """Render scenes.json `in_image_text[]` as a positive prompt block."""
    if not items:
        return ""
    lines: list[str] = []
    for it in items:
        text = it.get("text", "").strip()
        if not text:
            continue
        kind = it.get("kind", "sfx")
        style = it.get("style_hint") or "bold black katakana, manga onomatopoeia, expressive lettering"
        position_key = it.get("position", "")
        position = _POSITION_PHRASES.get(position_key, position_key.replace("-", " ") if position_key else "integrated naturally into the scene")
        if kind == "sfx":
            lines.append(f"- a manga sound effect \"{text}\" rendered as {style}, placed {position}")
        elif kind == "diegetic":
            lines.append(f"- a diegetic in-world inscription reading \"{text}\", {style}, placed {position}")
        else:
            lines.append(f"- visible text \"{text}\" rendered as {style}, placed {position}")
    if not lines:
        return ""
    body = "\n".join(lines)
    return f"INTEGRATED TEXT (drawn as part of the artwork — NOT inside a speech bubble):\n{body}"


def _format_safe_zones(zones: list[dict]) -> str:
    """Render scenes.json `bubble_safe_zones[]` as a negative-space prompt block."""
    if not zones:
        return ""
    lines: list[str] = []
    for z in zones:
        x = int(z.get("x_pct", 0))
        y = int(z.get("y_pct", 0))
        w = int(z.get("w_pct", 0))
        h = int(z.get("h_pct", 0))
        if w <= 0 or h <= 0:
            continue
        purpose = z.get("purpose")
        suffix = f" (reserved for a {purpose})" if purpose else ""
        lines.append(f"- a region around x={x}%, y={y}% spanning {w}%×{h}%{suffix}")
    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "NEGATIVE SPACE — keep these regions visually quiet (no faces, no fine "
        "detail, light or empty background) so a speech bubble can be overlaid later:\n" + body
    )


def compose_prompt(project: ProjectContext, panel: dict, scene_outfit: str | None) -> str:
    shot = panel["shot_type"].replace("_", " ")
    angle = panel["camera_angle"].replace("_", " ")
    comp = panel["composition"].replace("_", " ")
    eye = panel["eye_line"].replace("_", " ")
    emo1 = panel["emotion_primary"].replace("_", " ")
    emo2 = panel["emotion_secondary"].replace("_", " ")
    lighting = panel["lighting"].replace("_", " ")
    background = panel["background_style"].replace("_", " ")
    aspect = panel["aspect_ratio"]
    treatment = TREATMENT_HINTS.get(panel.get("treatment", "normal"), "")

    subject_lines: list[str] = []
    for c in panel.get("characters_in_panel", []):
        char = project.character(c["id"])
        desc = char.description_en if char else project.description_for(c["id"])
        # Outfit precedence: panel-level → scene-level → character default.
        outfit = c.get("outfit_en") or scene_outfit or (char.outfit_en if char else "")
        if outfit:
            desc = f"{desc}, wearing {outfit}"
        pose = c.get("pose", "natural_pose").replace("_", " ")
        direction = c.get("direction", "facing_camera").replace("_", " ")
        subject_lines.append(f"subject: {desc}, {pose}, {direction}")

    in_image = _format_in_image_text(panel.get("in_image_text") or [])
    safe_zones = _format_safe_zones(panel.get("bubble_safe_zones") or [])

    # Per-panel treatment can override the project's color style. For monochrome
    # treatments (symbolic_dark, monochrome, flashback_monochrome, photograph),
    # replace style.description with a treatment-matched monochrome line so the
    # prompt doesn't contradict itself ("color webtoon" + "monochrome treatment").
    treatment_key = panel.get("treatment", "normal")
    if treatment_key in _MONO_OVERRIDE_TREATMENTS:
        style_line = _MONO_STYLE_DESCRIPTIONS.get(treatment_key, project.style_description)
    else:
        style_line = project.style_description

    # Negative prompt: forbid speech-bubble dialogue text BUT allow the in_image_text
    # we explicitly asked for. So we don't include "text" alone — only the bubble forms.
    project_negative = project.style_negative or ""
    negative_terms: list[str] = []
    if project_negative:
        # Strip generic "text" if it appears alone in the project default — we replaced
        # it with the more specific phrasing below.
        for term in project_negative.split(","):
            t = term.strip()
            if t.lower() == "text":
                continue
            negative_terms.append(t)
    if not any("speech bubble" in t.lower() for t in negative_terms):
        negative_terms.append("speech bubbles")
    if not any("dialogue caption" in t.lower() or "captions" in t.lower() for t in negative_terms):
        negative_terms.append("dialogue captions")
    # Universal anatomy + style guards (added after ch1/ch2 review showed
    # systematic Gemini hallucinations).
    for guard in (
        "extra limbs",
        "extra arms",
        "extra fingers",
        "deformed hands",
        "anatomical errors",
        "photorealistic",
        "photograph",
        "live action",
        "3D render",
        "hyperreal",
    ):
        if not any(guard.lower() in t.lower() for t in negative_terms):
            negative_terms.append(guard)
    # Panels with no characters_in_panel: forbid stray people hallucinations.
    if not panel.get("characters_in_panel"):
        for guard in ("people", "human figures", "any person", "any character"):
            if not any(guard.lower() in t.lower() for t in negative_terms):
                negative_terms.append(guard)
    # If a monochrome treatment is active, also forbid stray color elements.
    if treatment_key in _MONO_OVERRIDE_TREATMENTS and not any("color" in t.lower() for t in negative_terms):
        negative_terms.append("color, vibrant hues")
    negative = ", ".join(negative_terms)

    lines = [
        f"{shot}, {angle} angle, {comp} composition",
        *subject_lines,
        f"expression: {emo1}, with undertone of {emo2}",
        f"eye line: {eye}",
        f"lighting: {lighting}",
        f"background: {background}",
        *([f"intent: {panel['intent']}"] if panel.get("intent") else []),
        *([treatment] if treatment else []),
        *([in_image] if in_image else []),
        *([safe_zones] if safe_zones else []),
        f"style: {style_line}",
        f"aspect ratio: {aspect}",
        f"negative: {negative}",
    ]
    return ",\n".join(line for line in lines if line)


def character_refs(project: ProjectContext, char_id: str) -> list[Path]:
    char = project.character(char_id)
    if char is None:
        return []
    base = char.char_dir(project.project_dir)
    refs: list[Path] = []
    for p in (
        char.stylesheet_turnaround(project.project_dir),
        char.stylesheet_expression(project.project_dir),
        char.selected_png(project.project_dir),
    ):
        if p.exists():
            refs.append(p)
    return refs


def panel_output_path(chapter: Chapter, panel_id: str) -> Path:
    scene_id = "_".join(panel_id.split("_")[:2])
    d = chapter.panels_dir / scene_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{panel_id}_best.png"


def resolve_reuse_from(project: ProjectContext, chapter: Chapter, ref: str) -> Path:
    """Resolve a `reuse_from` string. Tries chapter-relative, then project-relative, then absolute."""
    p = Path(ref)
    if p.is_absolute():
        return p
    # Chapter-relative (the new convention after migration)
    cand = chapter.work_dir / ref
    if cand.exists():
        return cand
    # Project-relative
    cand = project.project_dir / ref
    if cand.exists():
        return cand
    # Last resort: project.resolve_path uses repo root
    return project.resolve_path(ref)


def _plan_jobs(
    project: ProjectContext,
    chapter: Chapter,
    *,
    force: bool,
    scene_filter: str | None,
    use_prev_continuity: bool,
) -> tuple[list[tuple[str, Path, list[Path], str]], list[Path]]:
    """Walk scenes.json and return (jobs_to_run, skipped_existing_paths).

    Each job is (prompt, out_path, refs, panel_id). When `use_prev_continuity`
    is True the previous panel image is appended as a reference (sync mode); in
    batch mode that previous image may not exist yet at job-build time so it is
    omitted and identity is carried only by character stylesheet refs.
    """
    cfg = json.loads(chapter.scenes_json.read_text(encoding="utf-8"))
    jobs: list[tuple[str, Path, list[Path], str]] = []
    existing: list[Path] = []
    for scene in cfg["scenes"]:
        if scene_filter and scene["id"] != scene_filter:
            continue
        scene_outfit = scene.get("character_spec", {}).get("outfit_en")
        prev_best: Path | None = None
        for panel in scene["panels"]:
            pid = panel["panel_id"]
            reuse = panel.get("reuse_from")
            if reuse:
                src = resolve_reuse_from(project, chapter, reuse)
                existing.append(src)
                prev_best = src
                continue
            out = panel_output_path(chapter, pid)
            if out.exists() and not force:
                existing.append(out)
                prev_best = out
                continue
            prompt = compose_prompt(project, panel, scene_outfit)
            refs: list[Path] = []
            seen: set[str] = set()
            for c in panel.get("characters_in_panel", []):
                cid = c["id"]
                if cid in seen:
                    continue
                seen.add(cid)
                refs.extend(character_refs(project, cid))
            if use_prev_continuity and prev_best is not None and prev_best.exists():
                refs.append(prev_best)
            jobs.append((prompt, out, refs, pid))
            prev_best = out
    return jobs, existing


def render_chapter(
    project: ProjectContext,
    chapter: Chapter,
    *,
    force: bool = False,
    scene_filter: str | None = None,
    inter_call_delay_s: float = 6.0,
    use_batch: bool = False,
    poll_interval_s: float = 30.0,
) -> list[Path]:
    if not chapter.scenes_json.exists():
        raise FileNotFoundError(f"missing {chapter.scenes_json}")

    jobs, existing = _plan_jobs(
        project,
        chapter,
        force=force,
        scene_filter=scene_filter,
        use_prev_continuity=not use_batch,
    )

    if not jobs:
        print(f"nothing to render ({len(existing)} panels already present)")
        return existing

    if use_batch:
        print(f"\n=== batch render: {len(jobs)} new panels (skipping {len(existing)} existing) ===")
        simple_jobs = [(prompt, out, refs) for (prompt, out, refs, _pid) in jobs]
        written, failures = generate_images_batch(
            simple_jobs,
            poll_interval_s=poll_interval_s,
            display_name=f"{project.id}-{chapter.id}-{int(time.time())}",
        )
        for idx, msg in failures:
            print(f"  ⚠️ {jobs[idx][3]}: {msg}")
        return existing + written

    paths: list[Path] = list(existing)
    last_scene = None
    for prompt, out, refs, pid in jobs:
        scene_id = "_".join(pid.split("_")[:2])
        if scene_id != last_scene:
            print(f"\n=== {scene_id} ===")
            last_scene = scene_id
        print(f"\n  [{pid}] refs={len(refs)}")
        try:
            generate_image(prompt, out, reference_images=refs)
            paths.append(out)
        except Exception as e:
            print(f"  ⚠️ skipped {pid}: {e}")
        time.sleep(inter_call_delay_s)
    return paths


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python -m src.render_panels <project_id> <chapter_id> [<scene_id>] [--force] [--batch] [--poll-interval=SECONDS]",
            file=sys.stderr,
        )
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    force = "--force" in sys.argv
    use_batch = "--batch" in sys.argv
    poll_interval = 30.0
    for a in sys.argv:
        if a.startswith("--poll-interval="):
            poll_interval = float(a.split("=", 1)[1])
    scene_filter = next((a for a in sys.argv[3:] if not a.startswith("--")), None)
    render_chapter(
        project,
        chapter,
        force=force,
        scene_filter=scene_filter,
        use_batch=use_batch,
        poll_interval_s=poll_interval,
    )


if __name__ == "__main__":
    main()
