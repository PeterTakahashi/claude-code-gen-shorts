"""Daily routine uploader — picks N uploadable shorts per channel and uploads them.

For each channel:
  1. Determines its language and theme (from DB channels table)
  2. Lists all yamls in projects whose series.theme matches the channel theme
  3. Filters to ones where the local mp4 exists at
       projects/<series>/output/shorts/<sid>/<language>/short.mp4
  4. Excludes ones already live on this channel
     (DB row with this channel_id, metadata.deleted_at is null)
  5. Prefers previously-deleted-for-repost over never-uploaded (re-uploading
     deleted content first keeps the backlog rotating)
  6. Uploads up to N shorts via youtube_batch_upload_shorts logic
  7. SEO description is left to youtube_update_metadata (run separately)

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.daily_upload --per-channel 2
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.daily_upload --per-channel 2 --channel ijinden_ja
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.daily_upload --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .db import connect

ROOT = Path(__file__).resolve().parent.parent


def _list_active_video_sids(conn, channel_id: str) -> set[str]:
    """Return short_ids currently active (non-deleted) on this channel."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT metadata->>'short_id' FROM videos
               WHERE channel_id = %s AND kind = 'short'
                 AND superseded_by IS NULL
                 AND (metadata->>'deleted_at') IS NULL""",
            (channel_id,),
        )
        return {row[0] for row in cur.fetchall() if row[0]}


def _list_eligible_projects(conn, channel_theme: str) -> list[str]:
    """Return series.id list whose theme matches this channel theme."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM series WHERE theme = %s", (channel_theme,))
        return [row[0] for row in cur.fetchall()]


def _previously_deleted_sids(conn, channel_id: str) -> set[str]:
    """short_ids that were uploaded to this channel before but got deleted."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT metadata->>'short_id' FROM videos
               WHERE channel_id = %s AND kind = 'short'
                 AND (metadata->>'deleted_at') IS NOT NULL""",
            (channel_id,),
        )
        return {row[0] for row in cur.fetchall() if row[0]}


def pick_candidates(channel_id: str, language: str, theme: str, n: int) -> list[tuple[str, str, str]]:
    """Return [(project_id, short_id, mp4_path)] of up to n shorts ready to upload.

    Priority: previously-deleted (rotation) first, then never-uploaded, in
    project then short_id order for determinism.
    """
    with connect() as conn:
        active = _list_active_video_sids(conn, channel_id)
        prev_deleted = _previously_deleted_sids(conn, channel_id)
        projects = _list_eligible_projects(conn, theme)

    candidates_deleted: list[tuple[str, str, str]] = []
    candidates_fresh: list[tuple[str, str, str]] = []
    for proj in projects:
        shorts_dir = ROOT / "projects" / proj / "shorts"
        if not shorts_dir.exists():
            continue
        for yml in sorted(shorts_dir.glob("*.yaml")):
            sid = yml.stem
            if sid in active:
                continue
            mp4 = ROOT / "projects" / proj / "output" / "shorts" / sid / language / "short.mp4"
            if not mp4.exists():
                continue
            entry = (proj, sid, str(mp4))
            if sid in prev_deleted:
                candidates_deleted.append(entry)
            else:
                candidates_fresh.append(entry)

    return (candidates_deleted + candidates_fresh)[:n]


def run_upload(project_id: str, short_id: str, channel_id: str, language: str) -> int:
    """Invoke youtube_batch_upload_shorts as subprocess for a single short."""
    cmd = [
        ".venv/bin/python", "-m", "src.youtube_batch_upload_shorts",
        project_id,
        "--channel", channel_id,
        "--language", language,
        "--privacy", "public",
        "--only", short_id,
    ]
    print(f"  $ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT, env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--per-channel", type=int, default=2, help="how many shorts to upload per channel today")
    p.add_argument("--channel", default=None, help="restrict to one channel id")
    p.add_argument("--dry-run", action="store_true", help="show what would upload, don't actually upload")
    args = p.parse_args()

    with connect() as conn, conn.cursor() as cur:
        sql = "SELECT id, language, theme, display_name FROM channels"
        params: tuple = ()
        if args.channel:
            sql += " WHERE id = %s"
            params = (args.channel,)
        sql += " ORDER BY id"
        cur.execute(sql, params)
        channels = cur.fetchall()

    print(f"=== daily upload  per_channel={args.per_channel}  dry_run={args.dry_run} ===\n")
    failures: list[str] = []
    summary: list[str] = []
    for ch_id, lang, theme, display_name in channels:
        candidates = pick_candidates(ch_id, lang, theme, args.per_channel)
        print(f"[{ch_id}]  ({display_name})  theme={theme}  lang={lang}  picks={len(candidates)}")
        if not candidates:
            print(f"  (no eligible shorts — content backlog empty for theme={theme})")
            summary.append(f"  {ch_id:25s}  0/{args.per_channel}  ← BACKLOG EMPTY, create more content")
            continue
        for proj, sid, mp4 in candidates:
            print(f"  → {proj}/{sid}  ({Path(mp4).stat().st_size/1024/1024:.1f} MiB)")
        if args.dry_run:
            summary.append(f"  {ch_id:25s}  would upload {len(candidates)}/{args.per_channel}")
            continue
        uploaded = 0
        for proj, sid, _mp4 in candidates:
            rc = run_upload(proj, sid, ch_id, lang)
            if rc == 0:
                uploaded += 1
            else:
                failures.append(f"{ch_id}/{proj}/{sid}")
        summary.append(f"  {ch_id:25s}  {uploaded}/{args.per_channel} uploaded")
        print()

    print("\n=== summary ===")
    for line in summary:
        print(line)
    if failures:
        print(f"\n⚠️ {len(failures)} failures: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
