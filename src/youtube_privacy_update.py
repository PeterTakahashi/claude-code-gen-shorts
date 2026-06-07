"""Bulk-update the YouTube privacy status of every active video in the DB.

Active = not superseded. Use `--include-superseded` to include the duplicate
uploads as well (you almost certainly don't want this).

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_privacy_update --privacy public
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_privacy_update --privacy public --series stevejobs
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db import connect, list_active_videos
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--privacy", required=True, choices=["private", "unlisted", "public"])
    p.add_argument("--series", default=None)
    p.add_argument("--include-superseded", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    creds = get_credentials(args.client_secret, args.token, args.port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    with connect() as conn:
        if args.include_superseded:
            with conn.cursor() as cur:
                sql = "SELECT video_id, series_id, chapter_id, title FROM videos"
                params: tuple = ()
                if args.series:
                    sql += " WHERE series_id = %s"
                    params = (args.series,)
                cur.execute(sql, params)
                cols = [d.name for d in cur.description]
                videos = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            videos = list_active_videos(conn, args.series)

        if not videos:
            print("no videos to update")
            return 0

        print(f"updating {len(videos)} videos → {args.privacy}\n")
        success = 0
        for v in videos:
            vid = v["video_id"]
            label = f"{v['series_id']}/{v['chapter_id']}"
            if args.dry_run:
                print(f"  [dry-run] {vid}  {label}")
                continue
            try:
                # videos.update requires the full snippet+status. Fetch the
                # current snippet (the API rejects partial updates).
                cur_resp = youtube.videos().list(part="snippet,status", id=vid).execute()
                items = cur_resp.get("items", [])
                if not items:
                    print(f"  {vid}  {label}  ✗ not found on YouTube", file=sys.stderr)
                    continue
                snippet = items[0]["snippet"]
                # Strip fields the API rejects on update.
                snippet.pop("publishedAt", None)
                snippet.pop("thumbnails", None)
                snippet.pop("channelId", None)
                snippet.pop("channelTitle", None)
                snippet.pop("liveBroadcastContent", None)
                snippet.pop("localized", None)

                body = {
                    "id": vid,
                    "snippet": snippet,
                    "status": {
                        "privacyStatus": args.privacy,
                        "selfDeclaredMadeForKids": False,
                    },
                }
                youtube.videos().update(part="snippet,status", body=body).execute()
                with conn.cursor() as cur:
                    cur.execute("UPDATE videos SET privacy = %s WHERE video_id = %s", (args.privacy, vid))
                conn.commit()
                print(f"  {vid}  {label}  ✓ {args.privacy}")
                success += 1
                time.sleep(0.1)
            except HttpError as e:
                print(f"  {vid}  {label}  ✗ {e}", file=sys.stderr)

        print(f"\n{success}/{len(videos)} videos updated to {args.privacy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
