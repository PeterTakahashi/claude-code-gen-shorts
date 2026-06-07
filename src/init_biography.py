"""Bootstrap a new biography webtoon project.

Creates `projects/<id>/` with project.yaml + characters.yaml + lexicon.yaml +
input/ + characters/ + upload_metadata.json templates. After this, you typically:

  1. Edit project.yaml (title, era, locale_hint, chapters list)
  2. Edit characters.yaml (add your real cast — 3 life-stage variants + family)
  3. Optionally run plan_series.py to draft a 12-episode arc with Gemini
  4. For each chapter, write novel.txt + scenes.json + bubbles.json
  5. Run build_chapter or build_series

Usage:
  uv run python -m src.init_biography <project_id> --subject "氏名" --title-ja "シリーズ名"
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROJECT_YAML_TEMPLATE = textwrap.dedent("""\
    # {subject} biography — webtoon project.

    id: {pid}
    title_ja: "{title_ja}"
    title_en: "{title_en}"
    subject: "{subject}"
    author: "(imagined first-person memoir)"
    language: ja

    # Era / locale strings injected into every panel prompt.
    era: "{era}"
    locale_hint: "{locale_hint}"

    style:
      description: "full-color modern anime / webtoon style, soft cel shading, expressive line art, cinematic lighting, biographical drama tone"
      negative: "speech bubbles, dialogue captions, watermark, extra fingers, distorted face, samurai, kimono, asian period clothing, photorealistic, photograph, 3D render"

    # Multi-chapter biography. Add entries as you write each one.
    chapters:
      - id: ch1
        title: "第一話 ___"

    narrator:
      voice_style_id: 1310138977  # Aivis: 阿井田 茂 / Calm
      voice_speed: 0.95
      instructions: |
        Read as the subject in his/her later years, looking back on his/her own
        life with calm, reflective intensity. First-person memoir tone. Quiet,
        measured, contemplative.

    voice:
      engine: aivis
      endpoint: "http://127.0.0.1:10101"
      verify: false
      similarity_threshold: 0.88
      whisper:
        model: large-v3

    bubbles:
      font_path: /Users/apple/dev/claude-code/webtoon-gen/assets/fonts/NotoSansJP-Regular.otf
      font_index: 0
      font_scale: 4.0

    webtoon:
      width_px: 800
      panel_gap_px:
        tight: 20
        breath: 80
        jump: 200

    output_targets: []
    """)

CHARACTERS_YAML_TEMPLATE = textwrap.dedent("""\
    # Cast for the {subject} biographical short.
    # Three life-stage variants of the subject (child / young / mature) plus
    # family, partners, rivals. Voice settings are optional for non-narrator
    # characters (they fall back to project.narrator).

    characters:
      - id: subject_child
        name_ja: 主人公 (子供)
        description_en: "TODO — describe child appearance with characteristic facial features"
        outfit_en: "TODO — era-appropriate child outfit"
        voice_style_id: 1310138977
        voice_speed: 1.0
        voice_instructions: null
        selected_candidate: 1
        expressions: []
        poses: []

      - id: subject_young
        name_ja: 主人公 (青年期)
        description_en: "TODO"
        outfit_en: "TODO"
        voice_style_id: 1310138977
        voice_speed: 1.0
        voice_instructions: null
        selected_candidate: 1

      - id: subject_adult
        name_ja: 主人公 (壮年期)
        description_en: "TODO"
        outfit_en: "TODO"
        voice_style_id: 1310138977
        voice_speed: 1.0
        voice_instructions: null
        selected_candidate: 1

      # Add family, mentors, rivals here. Description-only is fine
      # (no individual stylesheet needed initially).
    """)

LEXICON_YAML_TEMPLATE = textwrap.dedent("""\
    # Pronunciation overrides for TTS and English / brand-name katakana mappings
    # used in subtitles. Add entries as needed.
    lexicon:
      # English brand names that should be spoken as katakana when read aloud
      # but kept as English in image prompts / subtitles.
      readings: {}
    """)

UPLOAD_META_TEMPLATE = textwrap.dedent("""\
    {{
      "series_name": "{title_ja}",
      "series_short": "{title_ja}",
      "default_privacy": "private",
      "default_tags": "{subject},biography,伝記,人物史,アニメ,ウェブトゥーン,webtoon",
      "common_description_footer": "\\n\\n──────────────\\nこの動画は12話完結の{title_ja}伝記アニメ・ウェブトゥーンです。",
      "chapters": [
        {{
          "id": "ch1",
          "title": "【{title_ja}】第1話 ___",
          "description": "TODO: 章の3-5行の要約"
        }}
      ]
    }}
    """)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("--subject", required=True, help="Subject person's full name in Japanese (e.g. スティーブ・ジョブズ)")
    p.add_argument("--title-ja", required=True, help="Series title in Japanese (e.g. スティーブ・ジョブズ伝)")
    p.add_argument("--title-en", default="", help="Series title in English")
    p.add_argument("--era", default="late 20th century", help="Era string for panel prompts")
    p.add_argument("--locale", default="USA", help="Locale hint for panel prompts (e.g. 'Silicon Valley California')")
    p.add_argument("--force", action="store_true", help="Overwrite existing project directory")
    args = p.parse_args()

    proj_dir = ROOT / "projects" / args.project_id
    if proj_dir.exists() and not args.force:
        print(f"ERROR: {proj_dir} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "input").mkdir(exist_ok=True)
    (proj_dir / "characters").mkdir(exist_ok=True)
    (proj_dir / "work" / "chapters" / "ch1").mkdir(parents=True, exist_ok=True)
    (proj_dir / "output").mkdir(exist_ok=True)

    files = {
        "project.yaml": PROJECT_YAML_TEMPLATE.format(
            pid=args.project_id,
            title_ja=args.title_ja,
            title_en=args.title_en or args.title_ja,
            subject=args.subject,
            era=args.era,
            locale_hint=args.locale,
        ),
        "characters.yaml": CHARACTERS_YAML_TEMPLATE.format(subject=args.subject),
        "lexicon.yaml": LEXICON_YAML_TEMPLATE,
        "upload_metadata.json": UPLOAD_META_TEMPLATE.format(
            title_ja=args.title_ja, subject=args.subject
        ),
    }
    for name, content in files.items():
        out = proj_dir / name
        if out.exists() and not args.force:
            print(f"  skip existing: {out}")
            continue
        out.write_text(content, encoding="utf-8")
        print(f"  wrote: {out}")

    print(f"\n✅ project bootstrapped: {proj_dir}")
    print("\nNext steps:")
    print(f"  1. Edit projects/{args.project_id}/project.yaml — fix era, locale_hint, add chapter list")
    print(f"  2. Edit projects/{args.project_id}/characters.yaml — fill in real cast")
    print(f"  3. (optional) uv run python -m src.plan_series {args.project_id}  # draft 12-episode arc")
    print(f"  4. Write novel.txt / scenes.json / bubbles.json under projects/{args.project_id}/work/chapters/ch1/")
    print(f"  5. uv run python -m src.build_chapter {args.project_id} ch1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
