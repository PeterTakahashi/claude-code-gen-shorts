"""One-shot migration of the legacy 人間失格-only layout into projects/ningen_shikkaku/.

Old layout (top-level):
  work/{novel.txt, scenes.json, scenes_ch2.json, bubbles_v2.json, bubbles_ch2.json,
        panel_positions*.json, panels/{beat,scene,ch2}_*/, audio_v2/, audio_ch2_v3/,
        pages/, pages_ch2/, video_segs/, video_segs_ch2/, characters/, ...}
  output/webtoon_{first,second}_memoir{,_scroll.mp4,.png}

New layout:
  projects/ningen_shikkaku/{project.yaml, characters.yaml, input/novel.txt,
        characters/, work/chapters/<ch>/, output/<ch>/}

Usage:
  uv run python -m src.migrate --dry-run   # default: list moves, no changes
  uv run python -m src.migrate --apply     # actually move
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .project import REPO_ROOT


PROJECT_ID = "ningen_shikkaku"
PROJECT_DIR = REPO_ROOT / "projects" / PROJECT_ID
WORK = REPO_ROOT / "work"
OUTPUT = REPO_ROOT / "output"


@dataclass
class Move:
    src: Path
    dst: Path
    kind: str  # "dir" or "file"

    def describe(self) -> str:
        return f"  [{self.kind:4s}] {self.src.relative_to(REPO_ROOT)}  →  {self.dst.relative_to(REPO_ROOT)}"


# ---------- chapter classification ----------

CH1_PANEL_PREFIXES = {"beat_001", "beat_002", "beat_003", "beat_004", "beat_005", "beat_006",
                      "scene_01", "scene_02", "scene_03", "scene_04", "scene_05", "scene_06",
                      "scene_07", "scene_08"}
CH2_PANEL_PREFIXES = {"ch2_01", "ch2_02", "ch2_03", "ch2_04", "ch2_05", "ch2_06", "ch2_07", "ch2_08"}


def chapter_for_panel_dir(name: str) -> str | None:
    if name in CH1_PANEL_PREFIXES:
        return "chapter_01"
    if name in CH2_PANEL_PREFIXES:
        return "chapter_02"
    return None


# ---------- pre-flight validation ----------

def preflight() -> list[str]:
    errs: list[str] = []
    must_exist = [
        WORK / "novel.txt",
        WORK / "novel_chapter2.txt",
        WORK / "scenes.json",
        WORK / "scenes_ch2.json",
        WORK / "bubbles_v2.json",
        WORK / "bubbles_ch2.json",
        WORK / "audio_v2",
        WORK / "audio_ch2_v3",
        WORK / "characters",
        OUTPUT / "webtoon_first_memoir.png",
        OUTPUT / "webtoon_first_memoir_scroll.mp4",
        OUTPUT / "webtoon_second_memoir.png",
        OUTPUT / "webtoon_second_memoir_scroll.mp4",
    ]
    for p in must_exist:
        if not p.exists():
            errs.append(f"missing: {p}")

    # scenes.json panel_id consistency: every non-reuse panel has a *_best.png on disk
    for scenes_name, panels_root in [("scenes.json", WORK / "panels"), ("scenes_ch2.json", WORK / "panels")]:
        try:
            data = json.loads((WORK / scenes_name).read_text(encoding="utf-8"))
        except Exception as e:
            errs.append(f"unreadable: {scenes_name}: {e}")
            continue
        for s in data.get("scenes", []):
            for p in s["panels"]:
                if p.get("reuse_from"):
                    src = REPO_ROOT / p["reuse_from"]
                    if not src.exists():
                        errs.append(f"reuse_from missing in {scenes_name}: {p['panel_id']} → {p['reuse_from']}")
                else:
                    pid = p["panel_id"]
                    scene_id = "_".join(pid.split("_")[:2])
                    cand = panels_root / scene_id / f"{pid}_best.png"
                    if not cand.exists():
                        errs.append(f"panel best.png missing in {scenes_name}: {cand}")

    return errs


# ---------- move planning ----------

def plan_moves() -> list[Move]:
    moves: list[Move] = []

    # 1. Characters (shared across chapters)
    moves.append(Move(WORK / "characters", PROJECT_DIR / "characters", "dir"))

    # 2. Per-chapter directories and JSONs
    chapter_map = [
        ("chapter_01", {
            "novel.txt": (WORK / "novel.txt", "file"),
            "scenes.json": (WORK / "scenes.json", "file"),
            "bubbles.json": (WORK / "bubbles_v2.json", "file"),
            "panel_positions.json": (WORK / "panel_positions.json", "file"),
            "audio": (WORK / "audio_v2", "dir"),
            "pages": (WORK / "pages", "dir"),
            "video_segs": (WORK / "video_segs", "dir"),
            "bubbled": (WORK / "bubbles_v2", "dir"),
            "strips": (WORK / "strips", "dir"),
            "webtoon_for_video.png": (WORK / "webtoon_for_video.png", "file"),
        }),
        ("chapter_02", {
            "novel.txt": (WORK / "novel_chapter2.txt", "file"),
            "scenes.json": (WORK / "scenes_ch2.json", "file"),
            "bubbles.json": (WORK / "bubbles_ch2.json", "file"),
            "panel_positions.json": (WORK / "panel_positions_ch2.json", "file"),
            "audio": (WORK / "audio_ch2_v3", "dir"),
            "pages": (WORK / "pages_ch2", "dir"),
            "video_segs": (WORK / "video_segs_ch2", "dir"),
            "bubbled": (WORK / "bubbles_ch2", "dir"),
            "webtoon_for_video.png": (WORK / "webtoon_ch2_for_video.png", "file"),
        }),
    ]
    for ch_id, items in chapter_map:
        ch_dir = PROJECT_DIR / "work" / "chapters" / ch_id
        for new_name, (src, kind) in items.items():
            if src.exists():
                moves.append(Move(src, ch_dir / new_name, kind))

    # 3. Panels — sort beat_*/scene_*/ch2_* into the right chapter
    panels_src_root = WORK / "panels"
    if panels_src_root.is_dir():
        for sub in sorted(panels_src_root.iterdir()):
            if not sub.is_dir():
                continue
            ch_id = chapter_for_panel_dir(sub.name)
            if ch_id is None:
                continue
            dst = PROJECT_DIR / "work" / "chapters" / ch_id / "panels" / sub.name
            moves.append(Move(sub, dst, "dir"))

    # 4. Final outputs
    output_map = [
        ("chapter_01/webtoon.png", OUTPUT / "webtoon_first_memoir.png"),
        ("chapter_01/webtoon_scroll.mp4", OUTPUT / "webtoon_first_memoir_scroll.mp4"),
        ("chapter_02/webtoon.png", OUTPUT / "webtoon_second_memoir.png"),
        ("chapter_02/webtoon_scroll.mp4", OUTPUT / "webtoon_second_memoir_scroll.mp4"),
    ]
    for new_rel, src in output_map:
        if src.exists():
            moves.append(Move(src, PROJECT_DIR / "output" / new_rel, "file"))

    return moves


# ---------- scenes.json reuse_from rewriting ----------

def rewrite_scenes_paths(scenes_path: Path) -> bool:
    """In a migrated scenes.json, rewrite reuse_from paths.

    Old: "work/panels/beat_001/beat_001_p01_best.png"
    New: "panels/beat_001/beat_001_p01_best.png"   (chapter-relative)

    Also strip ch2_ prefix nothing — those are already in their own chapter.
    Returns True if any rewrite occurred.
    """
    if not scenes_path.exists():
        return False
    data = json.loads(scenes_path.read_text(encoding="utf-8"))
    changed = False
    for s in data.get("scenes", []):
        for p in s["panels"]:
            ref = p.get("reuse_from")
            if not ref:
                continue
            new_ref = re.sub(r"^work/panels/", "panels/", ref)
            if new_ref != ref:
                p["reuse_from"] = new_ref
                changed = True
    if changed:
        scenes_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return changed


# ---------- input/novel.txt reconstruction ----------

def write_full_novel_input(apply: bool) -> Path:
    """Concatenate ch1 + ch2 extracts into projects/<id>/input/novel.txt.

    Both files already start with their own marker line ('第一の手記' / '第二の手記'),
    so simple concatenation is round-trippable through the chapter splitter.

    Reads from the *migrated* chapter dirs (sources have been moved by now).
    """
    dst = PROJECT_DIR / "input" / "novel.txt"
    if not apply:
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for ch in ("chapter_01", "chapter_02"):
        src = PROJECT_DIR / "work" / "chapters" / ch / "novel.txt"
        if src.exists():
            parts.append(src.read_text(encoding="utf-8").rstrip())
    dst.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return dst


# ---------- apply ----------

def apply_move(m: Move) -> None:
    m.dst.parent.mkdir(parents=True, exist_ok=True)
    if m.dst.exists():
        print(f"  ! dst exists, skipping: {m.dst}")
        return
    shutil.move(str(m.src), str(m.dst))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually perform the moves")
    ap.add_argument("--dry-run", action="store_true", help="print plan only (default)")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()

    apply = args.apply and not args.dry_run

    if not args.skip_preflight:
        errs = preflight()
        if errs:
            print("Pre-flight check failed:", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            print("\nUse --skip-preflight to override (NOT recommended).", file=sys.stderr)
            return 1
        print("Pre-flight: OK\n")

    moves = plan_moves()
    print(f"Planned moves ({len(moves)}):")
    for m in moves:
        print(m.describe())

    print(f"\n  [file] (synthesized) input/novel.txt  ←  work/novel.txt + work/novel_chapter2.txt")
    print(f"  [edit] {PROJECT_DIR.relative_to(REPO_ROOT)}/work/chapters/chapter_01/scenes.json — rewrite reuse_from paths")

    if not apply:
        print("\nDry run. Re-run with --apply to execute.")
        return 0

    print("\nExecuting…")
    for m in moves:
        if not m.src.exists():
            print(f"  ! src missing, skip: {m.src}")
            continue
        apply_move(m)
        print(f"  ✓ {m.dst.relative_to(REPO_ROOT)}")

    write_full_novel_input(apply=True)
    print(f"  ✓ input/novel.txt synthesized")

    ch1_scenes = PROJECT_DIR / "work" / "chapters" / "chapter_01" / "scenes.json"
    if rewrite_scenes_paths(ch1_scenes):
        print(f"  ✓ scenes.json reuse_from paths rewritten (chapter_01)")

    print("\n✅ Migration complete.")
    print("\nNext steps:")
    print("  1. Verify: ls projects/ningen_shikkaku/")
    print("  2. Clean up empty work/ output/ leftovers (run `find work output -type d -empty -delete`)")
    print("  3. Run: uv run python -m src.pipeline ningen_shikkaku")
    return 0


if __name__ == "__main__":
    sys.exit(main())
