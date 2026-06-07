"""Translate a JA short.yaml into English, adding/updating the `i18n.en` section.

Reads `projects/<project_id>/shorts/<short_id>.yaml`, asks Gemini to translate
the Japanese narration/captions/title/description into natural English suitable
for YouTube Shorts (concise hook, punchy script, viewer-friendly captions),
then writes back the updated yaml with `i18n.en.*` populated.

Idempotent: re-running re-translates and overwrites the i18n.en section.
Panels are left untouched (language-agnostic).

Usage:
  uv run python -m src.short_translate <project_id> <short_id>
  uv run python -m src.short_translate <project_id> --all
  uv run python -m src.short_translate <project_id> --all --target-language en
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .llm import extract_json, run_gemini_api

ROOT = Path(__file__).resolve().parent.parent


SYSTEM_PROMPT = """You are adapting a {source_lang_name} YouTube Shorts script into natural, punchy {target_lang_name}.

The video is a 25-40 second biographical Short. The viewer sees a series of panel images while the narrator speaks. The format is:
  - panels: a fixed library of images (identified by id, with English visual prompts)
  - narration: a list of TTS-spoken sentences, each pinned to one panel by id and shown with a short bottom caption
  - hook_caption: persistent top text
  - series_brand: small subtitle under the hook
  - title: YouTube title (ends with "#Shorts")
  - description: 2-3 lines + hashtags

Adaptation requirements (critical — this is not literal translation):
1. **Rewrite for natural {target_lang_name} flow, not word-for-word.** Sentence structure, idioms, and pacing differ between languages.
2. **You may reorder the narration to choose a different panel sequence**, as long as every narration line still references a valid panel id from the library. Same images, different storytelling order is fine.
3. **Panel library is READ-ONLY.** You MUST NOT invent new panel ids, you MUST NOT add panels, you MUST NOT modify existing panel ids or prompts. Every `panel:` value in your output narration MUST be one of the ids listed in the library below — exact match. Image regeneration is prohibited; reuse the exact panel set.
4. You may **merge or split** narration lines if it improves the flow (still 4-7 lines total typical). It is OK if some panels are referenced by zero narration lines — they will play silently. It is OK if one panel is referenced by multiple consecutive lines.
5. Each line should take ~3-7 sec when TTS-spoken at normal speed.
6. Captions: short (under ~30 chars of {target_lang_name}). Skip a caption (empty string) if redundant.
7. Preserve proper nouns in their {target_lang_name}-conventional form (Steve Jobs → スティーブ・ジョブズ; Apple → Apple).
8. Numbers in Arabic numerals.
9. Hook caption is the #1 reason to keep watching — make it a curiosity hook in {target_lang_name}, not a translation.
10. Title ends with "#Shorts". Description has 3-5 hashtags including #Shorts.

Panel library (id → English visual description):
{panel_library}

Source ({source_lang_name}) JSON:
{source_json}

Output strictly one JSON object (no markdown, no commentary):
{{
  "title": "...",
  "description": "...",
  "hook_caption": "...",
  "series_brand": "...",
  "voice_speaker": "Ryan",     // for en only: Ryan or Aiden; omit for non-en
  "voice_speed": 1.4,            // for ja only: Aivis speed multiplier; omit for non-ja
  "narration": [
    {{"panel": "<id from library>", "text": "...", "caption": "..."}},
    ...
  ]
}}
"""


def _build_panel_library_block(cfg: dict) -> str:
    """Return a readable summary of the panel library for the LLM prompt."""
    lines = []
    for i, p in enumerate(cfg.get("panels", [])):
        pid = p.get("id") or f"p{i+1}"
        prompt_snippet = (p.get("prompt") or p.get("source") or "")[:200].replace("\n", " ").strip()
        lines.append(f"  - {pid}: {prompt_snippet}")
    return "\n".join(lines) if lines else "  (no panels)"


def translate_yaml(cfg: dict, *, source_lang: str, target_lang: str,
                   source_lang_name: str, target_lang_name: str) -> dict:
    """Return a translated language-section dict adapted from source_lang content."""
    src_section = cfg.get(source_lang) if isinstance(cfg.get(source_lang), dict) else None
    if src_section is None:
        # v1 backward compat: source = top-level (assume ja in v1)
        if source_lang == "ja":
            src_section = {
                "title": cfg.get("title", ""),
                "description": cfg.get("description", ""),
                "hook_caption": cfg.get("hook_caption", ""),
                "series_brand": cfg.get("series_brand", ""),
                "narration": cfg.get("narration", []),
            }
        else:
            raise ValueError(f"yaml has no `{source_lang}:` section to translate from")

    panel_library = _build_panel_library_block(cfg)

    prompt = SYSTEM_PROMPT.format(
        source_lang_name=source_lang_name,
        target_lang_name=target_lang_name,
        panel_library=panel_library,
        source_json=json.dumps(src_section, ensure_ascii=False, indent=2),
    )
    raw = run_gemini_api(prompt, response_mime_type="application/json")
    j = extract_json(raw)
    out = json.loads(j)

    # Hard validation: every narration panel ref MUST be in the existing panel library.
    # New panel ids are prohibited (image regen is not allowed across language variants).
    valid_ids = {p.get("id") for p in cfg.get("panels", []) if isinstance(p, dict) and p.get("id")}
    if valid_ids:
        invalid = []
        for i, seg in enumerate(out.get("narration", [])):
            ref = seg.get("panel")
            if ref and ref not in valid_ids:
                invalid.append((i, ref))
        if invalid:
            details = ", ".join(f"narration[{i}].panel={ref!r}" for i, ref in invalid)
            raise ValueError(
                f"LLM returned narration referencing unknown panel ids ({details}). "
                f"Valid ids: {sorted(valid_ids)}. Panel library is read-only — re-run translation."
            )
    return out


def translate_short(project_id: str, short_id: str, *,
                    source_lang: str = "en", target_lang: str = "ja") -> Path:
    cfg_path = ROOT / "projects" / project_id / "shorts" / f"{short_id}.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(cfg_path)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    name_map = {"en": "English", "ja": "Japanese", "zh": "Chinese (Mandarin)", "ko": "Korean",
                "de": "German", "fr": "French", "es": "Spanish", "pt": "Portuguese"}
    src_name = name_map.get(source_lang, source_lang)
    tgt_name = name_map.get(target_lang, target_lang)

    translated = translate_yaml(
        cfg, source_lang=source_lang, target_lang=target_lang,
        source_lang_name=src_name, target_lang_name=tgt_name,
    )
    for k in ("title", "hook_caption", "narration"):
        if k not in translated:
            raise RuntimeError(f"{short_id}: translation missing field {k!r}")

    # Write into v2 top-level language section
    cfg[target_lang] = translated

    cfg_path.write_text(
        yaml.dump(cfg, sort_keys=False, allow_unicode=True, default_flow_style=False, width=200),
        encoding="utf-8",
    )
    print(f"  ✓ {short_id} → `{target_lang}:` added ({len(translated.get('narration', []))} segments)")
    return cfg_path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("short_id", nargs="?", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--source-lang", default="en",
                   help="Source language code (default 'en' — recommended primary). "
                        "v1 yaml falls back to top-level fields if source-lang section absent.")
    p.add_argument("--target-lang", default="ja",
                   help="Target language code (default 'ja').")
    args = p.parse_args()

    shorts_dir = ROOT / "projects" / args.project_id / "shorts"
    if args.all:
        ids = sorted(f.stem for f in shorts_dir.glob("*.yaml"))
    elif args.short_id:
        ids = [args.short_id]
    else:
        print("ERROR: provide short_id or --all", file=sys.stderr)
        return 2

    failures: list[tuple[str, str]] = []
    for sid in ids:
        print(f"\n=== adapting {args.project_id}/{sid}  {args.source_lang} → {args.target_lang} ===")
        try:
            translate_short(args.project_id, sid,
                            source_lang=args.source_lang,
                            target_lang=args.target_lang)
        except Exception as e:
            print(f"  ❌ FAILED: {e}", file=sys.stderr)
            failures.append((sid, str(e)))
    if failures:
        print(f"\n⚠️ {len(failures)} short(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
