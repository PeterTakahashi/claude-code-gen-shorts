"""Build every chapter listed in `<project>/project.yaml`.

Iterates project.chapters and runs `build_chapter` on each one. Stages within a
chapter are skipped if their output exists (unless --force).

Usage:
  uv run python -m src.build_series <project_id>
  uv run python -m src.build_series <project_id> --series "ジョブズ伝" --from ch5
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from .project import load


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("--from", dest="start_at", default=None, help="Start at this chapter id (inclusive)")
    p.add_argument("--only", default=None, help="Comma-separated chapter ids to build")
    p.add_argument("--force", action="store_true")
    p.add_argument("--skip-render", action="store_true")
    p.add_argument("--series", default=None)
    args = p.parse_args()

    project = load(args.project_id)
    chapter_ids = [c.id for c in project.chapters]

    if args.only:
        wanted = {c.strip() for c in args.only.split(",") if c.strip()}
        chapter_ids = [cid for cid in chapter_ids if cid in wanted]
    elif args.start_at:
        if args.start_at not in chapter_ids:
            print(f"ERROR: --from {args.start_at} not in {chapter_ids}", file=sys.stderr)
            return 1
        idx = chapter_ids.index(args.start_at)
        chapter_ids = chapter_ids[idx:]

    print(f"=== build_series: {args.project_id}  {len(chapter_ids)} chapter(s)  ===")
    print(f"    chapters: {', '.join(chapter_ids)}\n")

    totals_started = time.time()
    failures: list[tuple[str, int]] = []
    for cid in chapter_ids:
        cmd = [sys.executable, "-m", "src.build_chapter", args.project_id, cid]
        if args.force:
            cmd.append("--force")
        if args.skip_render:
            cmd.append("--skip-render")
        if args.series:
            cmd += ["--series", args.series]
        print(f"\n┌─── {cid} ────────────────────────────────────────")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"└─── {cid} FAILED (exit {r.returncode}) — continuing\n")
            failures.append((cid, r.returncode))
        else:
            print(f"└─── {cid} done\n")

    total = time.time() - totals_started
    print(f"\n=== build_series done in {total/60:.1f} min ===")
    if failures:
        print(f"failures: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
