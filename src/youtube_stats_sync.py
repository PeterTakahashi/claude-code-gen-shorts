"""Fetch YouTube Data API statistics for every active video in the DB and
append a snapshot to `video_stats`.

The YouTube Data v3 `videos.list` endpoint returns view / like / comment counts
publicly. **dislikeCount was removed from public responses in late 2021**, so
we fetch dislikes per-video via the YouTube Analytics API (requires the
yt-analytics.readonly scope and channel ownership).

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_stats_sync
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_stats_sync --series stevejobs
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_stats_sync --include-superseded
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_stats_sync --skip-dislikes

Schedule periodically (cron or launchd) to build a time series for analytics.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db import connect, insert_stats, list_active_videos
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN

BATCH = 50


def _fetch_dislikes(analytics, video_ids: list[str], start_date: str, end_date: str) -> dict[str, int]:
    """Return {video_id: dislikes} via YouTube Analytics API. Empty dict on failure."""
    if not video_ids:
        return {}
    out: dict[str, int] = {}
    # Analytics API filter has a length limit; chunk video_ids defensively.
    for i in range(0, len(video_ids), 200):
        chunk = video_ids[i:i + 200]
        try:
            resp = analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="dislikes",
                dimensions="video",
                filters="video==" + ",".join(chunk),
                maxResults=200,
            ).execute()
        except HttpError as e:
            print(f"  WARN: analytics dislikes query failed: {e}", file=sys.stderr)
            continue
        for row in resp.get("rows", []):
            # row = [video_id, dislikes_int]
            out[row[0]] = int(row[1])
    return out


def _chunk(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--series", default=None)
    p.add_argument("--include-superseded", action="store_true",
                   help="Also fetch stats for old/duplicate videos")
    p.add_argument("--skip-dislikes", action="store_true",
                   help="Skip the YouTube Analytics dislikes query (avoids the yt-analytics.readonly scope)")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    creds = get_credentials(args.client_secret, args.token, args.port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    analytics = None
    if not args.skip_dislikes:
        try:
            analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        except Exception as e:
            print(f"  WARN: analytics client build failed; skipping dislikes: {e}", file=sys.stderr)

    with connect() as conn:
        if args.include_superseded:
            with conn.cursor() as cur:
                sql = "SELECT video_id FROM videos"
                params: tuple = ()
                if args.series:
                    sql += " WHERE series_id = %s"
                    params = (args.series,)
                cur.execute(sql, params)
                video_ids = [row[0] for row in cur.fetchall()]
        else:
            video_ids = [v["video_id"] for v in list_active_videos(conn, args.series)]

        if not video_ids:
            print("no videos to sync")
            return 0

        # Look up the earliest video uploaded_at to set Analytics start_date.
        # Always go back at least 7 days from today — Analytics has 1-2 day data
        # latency, and a single-day window can return zero rows.
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(uploaded_at)::date FROM videos WHERE video_id = ANY(%s)", (video_ids,))
            min_date = cur.fetchone()[0] or date.today() - timedelta(days=30)
        today = date.today()
        start_floor = today - timedelta(days=7)
        start_date = min(min_date, start_floor).isoformat()
        end_date = today.isoformat()

        dislikes_map: dict[str, int] = {}
        if analytics:
            print(f"  fetching dislikes via Analytics API ({start_date} → {end_date}) …")
            dislikes_map = _fetch_dislikes(analytics, video_ids, start_date, end_date)
            print(f"  got dislikes for {len(dislikes_map)} videos")

        print(f"syncing stats for {len(video_ids)} videos…")
        total = 0
        for chunk in _chunk(video_ids, BATCH):
            try:
                resp = youtube.videos().list(
                    part="statistics,snippet,contentDetails",
                    id=",".join(chunk),
                    maxResults=BATCH,
                ).execute()
            except HttpError as e:
                print(f"  error: {e}", file=sys.stderr)
                continue

            for item in resp.get("items", []):
                vid = item["id"]
                stats = item.get("statistics", {})
                dl = dislikes_map.get(vid)
                insert_stats(
                    conn,
                    video_id=vid,
                    view_count=int(stats["viewCount"]) if "viewCount" in stats else None,
                    like_count=int(stats["likeCount"]) if "likeCount" in stats else None,
                    dislike_count=dl,
                    comment_count=int(stats["commentCount"]) if "commentCount" in stats else None,
                    favorite_count=int(stats["favoriteCount"]) if "favoriteCount" in stats else None,
                    raw=item,
                )
                total += 1
                vc = stats.get("viewCount", "?")
                lc = stats.get("likeCount", "?")
                cc = stats.get("commentCount", "?")
                dl_str = str(dl) if dl is not None else "—"
                print(f"  {vid}: views={vc} likes={lc} dislikes={dl_str} comments={cc}")
            conn.commit()
            time.sleep(0.1)

        print(f"\ninserted {total} stats rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
