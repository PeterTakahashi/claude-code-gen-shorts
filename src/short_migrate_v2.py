"""Migrate v1 short yamls (top-level narration + i18n.en) → v2 (panels[].id + per-lang sections).

Idempotent. Skips files already in v2 format.

Usage:
  uv run python -m src.short_migrate_v2 <project_id> [--dry-run]
  uv run python -m src.short_migrate_v2 --all-projects [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _slugify_for_id(text: str, idx: int) -> str:
    """Produce a panel id like 'p1' or a short slug from the first words of the prompt."""
    if not text:
        return f"p{idx + 1}"
    head = text.strip().splitlines()[0][:50]
    safe = "".join(c if c.isalnum() else "_" for c in head).strip("_")[:30]
    return safe or f"p{idx + 1}"


def is_v2(cfg: dict) -> bool:
    for lang in ("en", "ja"):
        if isinstance(cfg.get(lang), dict) and "narration" in cfg[lang]:
            return True
    return any(isinstance(p, dict) and "id" in p for p in cfg.get("panels", []))


def migrate_yaml(cfg: dict) -> dict:
    """Return a new dict in v2 form."""
    new: dict = {}
    if "id" in cfg:
        new["id"] = cfg["id"]
    if "parent_chapter" in cfg:
        new["parent_chapter"] = cfg["parent_chapter"]

    # Convert panels: positional → id'd (use auto p1..pN by default)
    panels = cfg.get("panels", [])
    new_panels = []
    panel_ids: list[str] = []
    for i, p in enumerate(panels):
        if isinstance(p, dict):
            pid = p.get("id") or f"p{i+1}"
            np = {"id": pid}
            if "prompt" in p:
                np["prompt"] = p["prompt"]
            elif "source" in p:
                np["source"] = p["source"]
            new_panels.append(np)
            panel_ids.append(pid)
    new["panels"] = new_panels

    # ja section from old top-level fields
    ja: dict = {}
    for k in ("title", "description", "hook_caption", "series_brand"):
        if k in cfg:
            ja[k] = cfg[k]
    if "voice_speed" in cfg:
        ja["voice_speed"] = cfg["voice_speed"]
    ja_narr = cfg.get("narration", []) or []
    ja_narr_v2 = []
    for i, seg in enumerate(ja_narr):
        if i < len(panel_ids):
            seg_v2 = {"panel": panel_ids[i]}
        else:
            seg_v2 = {}
        if isinstance(seg, dict):
            if "text" in seg:
                seg_v2["text"] = seg["text"]
            if "caption" in seg:
                seg_v2["caption"] = seg["caption"]
        ja_narr_v2.append(seg_v2)
    if ja_narr_v2:
        ja["narration"] = ja_narr_v2
    if ja:
        new["ja"] = ja

    # en section from i18n.en (old format)
    i18n = cfg.get("i18n") or {}
    if "en" in i18n:
        en_src = i18n["en"]
        en: dict = {}
        for k in ("title", "description", "hook_caption", "series_brand"):
            if k in en_src:
                en[k] = en_src[k]
        en_narr = en_src.get("narration", []) or []
        en_narr_v2 = []
        for i, seg in enumerate(en_narr):
            seg_v2 = {"panel": panel_ids[i]} if i < len(panel_ids) else {}
            if isinstance(seg, dict):
                if "text" in seg:
                    seg_v2["text"] = seg["text"]
                if "caption" in seg:
                    seg_v2["caption"] = seg["caption"]
            en_narr_v2.append(seg_v2)
        if en_narr_v2:
            en["narration"] = en_narr_v2
        if en:
            new["en"] = en

    return new


def migrate_file(path: Path, *, dry_run: bool = False) -> str:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if is_v2(cfg):
        return "already-v2"
    new = migrate_yaml(cfg)
    if dry_run:
        return "would-migrate"
    path.write_text(
        yaml.dump(new, sort_keys=False, allow_unicode=True, default_flow_style=False, width=200),
        encoding="utf-8",
    )
    return "migrated"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id", nargs="?", default=None)
    p.add_argument("--all-projects", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    projects: list[str]
    if args.all_projects:
        projects = sorted(p.name for p in (ROOT / "projects").iterdir()
                          if (p / "shorts").is_dir() and p.name != "_template")
    elif args.project_id:
        projects = [args.project_id]
    else:
        print("ERROR: provide project_id or --all-projects", file=sys.stderr)
        return 2

    summary = {"already-v2": 0, "migrated": 0, "would-migrate": 0}
    for pid in projects:
        shorts_dir = ROOT / "projects" / pid / "shorts"
        if not shorts_dir.exists():
            continue
        for yml in sorted(shorts_dir.glob("*.yaml")):
            result = migrate_file(yml, dry_run=args.dry_run)
            summary[result] = summary.get(result, 0) + 1
            print(f"  {result:14s}  {pid}/{yml.stem}")
    print(f"\nsummary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
