"""Delete a video from YouTube and clean up local DB + filesystem traces.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_video_delete <video_id> [--project <pid>] [--short-id <sid>]

If --project + --short-id are given, also removes:
  - DB row in videos
  - line in projects/<pid>/.youtube_shorts_uploads.json
  - local files under projects/<pid>/output/shorts/<sid>/
  - the source yaml under projects/<pid>/shorts/<sid>.yaml
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("--project", default=None)
    p.add_argument("--short-id", dest="short_id", default=None)
    p.add_argument("--keep-local", action="store_true", help="Skip local file removal")
    args = p.parse_args()

    creds = get_credentials(DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN, 8080)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    # 1. Delete from YouTube
    try:
        youtube.videos().delete(id=args.video_id).execute()
        print(f"  ✓ YouTube: deleted {args.video_id}")
    except HttpError as e:
        if e.resp.status == 404:
            print(f"  - YouTube: {args.video_id} not found (already gone)")
        else:
            print(f"  ✗ YouTube error: {e}", file=sys.stderr)
            return 1

    # 2. Remove DB row
    with connect() as conn:
        cur = conn.execute("DELETE FROM videos WHERE video_id = %s", (args.video_id,))
        if cur.rowcount:
            print(f"  ✓ DB: removed videos row")
        conn.commit()

    if not args.project or not args.short_id:
        return 0

    proj_dir = ROOT / "projects" / args.project

    # 3. Remove entry from .youtube_shorts_uploads.json
    log_path = proj_dir / ".youtube_shorts_uploads.json"
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
        if args.short_id in log.get("uploads", {}):
            del log["uploads"][args.short_id]
            log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ✓ log: removed {args.short_id} from {log_path.name}")

    if args.keep_local:
        return 0

    # 4. Remove output dir + yaml
    out = proj_dir / "output" / "shorts" / args.short_id
    if out.exists():
        shutil.rmtree(out)
        print(f"  ✓ removed: {out}")
    work = proj_dir / "work" / "shorts" / args.short_id
    if work.exists():
        shutil.rmtree(work)
        print(f"  ✓ removed: {work}")
    yml = proj_dir / "shorts" / f"{args.short_id}.yaml"
    if yml.exists():
        yml.unlink()
        print(f"  ✓ removed: {yml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
