"""Generate N character-sheet candidate images per character via Gemini.

Reads characters.yaml — one parametric template builds the prompt from
{description_en, outfit_en, era, style.description}. No per-novel prompt
hardcoding lives in code.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .image_generator import generate_image
from .project import Character, ProjectContext, load


CANDIDATE_TEMPLATE = """Character sheet reference, front view, neutral expression, full body.
Subject: {description}. He/she wears {outfit}.
Era: {era}.
Style: {style}.
Background: plain near-white background with only a faint floor shadow; NO scenery, NO other characters.
Lighting: soft even studio lighting, gentle shadow under the feet.
Aspect ratio: 3:4.
Do not include: text, labels, captions, speech bubbles, watermarks, extra characters, distorted anatomy, extra fingers."""


def candidate_prompt(project: ProjectContext, character: Character) -> str:
    return CANDIDATE_TEMPLATE.format(
        description=character.description_en,
        outfit=character.outfit_en or "era-appropriate clothing",
        era=project.era,
        style=project.style_description,
    )


def generate_candidates(
    project: ProjectContext,
    character: Character,
    n: int = 4,
    inter_call_delay_s: float = 6.0,
    force: bool = False,
) -> list[Path]:
    out_dir = character.candidates_dir(project.project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = candidate_prompt(project, character)

    paths: list[Path] = []
    for i in range(1, n + 1):
        out = out_dir / f"candidate_{i}.png"
        if out.exists() and not force:
            paths.append(out)
            continue
        print(f"[{character.id}] generating {i}/{n} → {out}")
        generate_image(prompt, out)
        paths.append(out)
        if i < n:
            time.sleep(inter_call_delay_s)
    return paths


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.character_designer <project_id> [<character_id>] [--force]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    force = "--force" in sys.argv
    char_id = next((a for a in sys.argv[2:] if not a.startswith("--")), None)

    targets = [project.character(char_id)] if char_id else project.characters
    targets = [c for c in targets if c is not None]
    if not targets:
        raise SystemExit(f"no character {char_id!r} in {project.id}")

    for c in targets:
        generate_candidates(project, c, force=force)


if __name__ == "__main__":
    main()
