"""Bootstrap a shorts-only project skeleton (no long-form chapters).

Just creates the minimal files needed by short_gen.py:
  - project.yaml (narrator + bubble fonts)
  - characters.yaml (subject character with 1-2 life stages)
  - shorts/ directory (empty — to be filled by an agent)
  - upload_metadata.json (series-level metadata)

Run for each of the new shorts-only people.
"""
from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROJECT_YAML = textwrap.dedent("""\
    # {subject} shorts-only project. No long-form chapters yet.
    id: {pid}
    title_ja: "{title_ja}"
    title_en: "{title_en}"
    subject: "{subject}"
    language: ja

    era: "{era}"
    locale_hint: "{locale}"

    style:
      description: "full-color modern anime / webtoon style, soft cel shading, expressive line art, cinematic lighting, biographical drama tone"
      negative: "speech bubbles, dialogue captions, watermark, extra fingers, distorted face, photorealistic, photograph, 3D render"

    chapters: []

    narrator:
      voice_style_id: 1310138977
      voice_speed: 1.0
      instructions: |
        Read with calm reflective intensity, first-person memoir tone.

    voice:
      engine: aivis
      endpoint: "http://127.0.0.1:10101"

    bubbles:
      font_path: /Users/apple/dev/claude-code/webtoon-gen/assets/fonts/NotoSansJP-Regular.otf
      font_index: 0
      font_scale: 4.0

    output_targets: []
    """)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("--subject", required=True)
    p.add_argument("--title-ja", required=True)
    p.add_argument("--title-en", default="")
    p.add_argument("--era", default="late 20th and early 21st century")
    p.add_argument("--locale", default="USA / global tech industry")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    proj_dir = ROOT / "projects" / args.project_id
    if proj_dir.exists() and (proj_dir / "project.yaml").exists() and not args.force:
        print(f"  exists: {proj_dir}/project.yaml  (use --force to overwrite)")
        return 0

    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "shorts").mkdir(exist_ok=True)
    (proj_dir / "output").mkdir(exist_ok=True)
    (proj_dir / "work").mkdir(exist_ok=True)

    (proj_dir / "project.yaml").write_text(
        PROJECT_YAML.format(
            pid=args.project_id,
            title_ja=args.title_ja,
            title_en=args.title_en or args.title_ja,
            subject=args.subject,
            era=args.era,
            locale=args.locale,
        ),
        encoding="utf-8",
    )
    # Characters.yaml will be hand-written per subject because the visual
    # description must be specific to that person's iconic features.
    chars_path = proj_dir / "characters.yaml"
    if not chars_path.exists() or args.force:
        chars_path.write_text(
            f'# {args.subject} cast — fill description_en with specific facial features.\n'
            f'characters: []\n',
            encoding="utf-8",
        )
    print(f"  bootstrapped: {proj_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
