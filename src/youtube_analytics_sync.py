"""Fetch YouTube Analytics for active videos (per-channel auth required).

Two report types:
  1. **summary**: avg_view_duration, avg_view_percentage, est_minutes_watched
     → upserted to `video_analytics`
  2. **retention curve**: audienceWatchRatio per elapsedVideoTimeRatio bucket
     → upserted to `video_retention`

Both require the `yt-analytics.readonly` scope (we already have it on all channel tokens).

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_analytics_sync                # all channels
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_analytics_sync --channel ijinden_ja
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_analytics_sync --no-retention # summary only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, resolve_channel_token


def _list_channels(conn, only_channel: str | None) -> list[tuple[str, str]]:
    """Return [(channel_id, token_file_path)] for all channels (or one)."""
    with conn.cursor() as cur:
        sql = "SELECT id, oauth_token_file FROM channels WHERE oauth_token_file IS NOT NULL"
        params: tuple = ()
        if only_channel:
            sql += " AND id = %s"
            params = (only_channel,)
        cur.execute(sql, params)
        return cur.fetchall()


def _videos_on_channel(conn, channel_id: str, days_back: int = 30) -> list[tuple[str, str]]:
    """Active short_id list for this channel uploaded in the last N days."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT video_id, COALESCE(title, '')
               FROM videos
               WHERE channel_id = %s
                 AND superseded_by IS NULL
                 AND (metadata->>'deleted_at') IS NULL
                 AND uploaded_at > NOW() - (%s || ' days')::interval
               ORDER BY uploaded_at DESC""",
            (channel_id, str(days_back)),
        )
        return cur.fetchall()


def fetch_summary(analytics, video_id: str, start_date: str, end_date: str) -> dict | None:
    """Lifetime summary metrics for one video."""
    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
            filters=f"video=={video_id}",
        ).execute()
    except HttpError as e:
        print(f"  [{video_id}] summary failed: {e}", file=sys.stderr)
        return None
    rows = resp.get("rows", [])
    if not rows:
        return None
    cols = [c["name"] for c in resp.get("columnHeaders", [])]
    return dict(zip(cols, rows[0]))


def fetch_retention(analytics, video_id: str, start_date: str, end_date: str) -> list[dict] | None:
    """Retention curve (audienceWatchRatio per 0-1.0 elapsed-time bucket)."""
    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
            sort="elapsedVideoTimeRatio",
            maxResults=400,
        ).execute()
    except HttpError as e:
        msg = str(e)
        # retention data not yet available for very fresh videos
        if "audienceWatchRatio" in msg or "404" in msg or "Insufficient" in msg:
            return None
        print(f"  [{video_id}] retention failed: {e}", file=sys.stderr)
        return None
    rows = resp.get("rows", [])
    if not rows:
        return None
    out = []
    for r in rows:
        elapsed, watch_ratio = r[0], r[1]
        rel_perf = r[2] if len(r) > 2 else None
        out.append({
            "elapsed_pct": float(elapsed) * 100.0,
            "watch_ratio": float(watch_ratio),
            "relative_perf": float(rel_perf) if rel_perf is not None else None,
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channel", default=None, help="restrict to one channel id")
    p.add_argument("--days-back", type=int, default=30,
                   help="how far back to pull analytics from (default 30 days)")
    p.add_argument("--no-retention", action="store_true",
                   help="skip retention curve (faster, summary only)")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=args.days_back)).isoformat()

    with connect() as conn:
        channels = _list_channels(conn, args.channel)

    total_summary = 0
    total_retention = 0
    for ch_id, token_file in channels:
        token_path = Path(token_file)
        if not token_path.is_absolute():
            token_path = Path(__file__).resolve().parent.parent / token_path
        if not token_path.exists():
            print(f"[{ch_id}] no token, skipping")
            continue
        try:
            creds = get_credentials(args.client_secret, token_path, args.port)
        except Exception as e:
            print(f"[{ch_id}] auth failed: {e}", file=sys.stderr)
            continue
        analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

        with connect() as conn2:
            videos = _videos_on_channel(conn2, ch_id, days_back=args.days_back)
        print(f"\n[{ch_id}]  {len(videos)} videos to analyze")

        for vid, title in videos:
            s = fetch_summary(analytics, vid, start_date, end_date)
            if s:
                with connect() as conn3, conn3.cursor() as cur3:
                    cur3.execute(
                        """INSERT INTO video_analytics
                              (video_id, date, views, est_minutes_watched,
                               avg_view_duration_sec, avg_view_percentage, raw)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (vid, end_date,
                         int(s.get("views") or 0),
                         float(s.get("estimatedMinutesWatched") or 0),
                         float(s.get("averageViewDuration") or 0),
                         float(s.get("averageViewPercentage") or 0),
                         json.dumps(s)),
                    )
                    conn3.commit()
                total_summary += 1
                print(f"  [{vid}] avg_dur={s.get('averageViewDuration', 0):.1f}s "
                      f"avg_pct={s.get('averageViewPercentage', 0):.1f}%  "
                      f"watched_min={s.get('estimatedMinutesWatched', 0):.1f}  "
                      f"{title[:30]}")

            if not args.no_retention:
                r = fetch_retention(analytics, vid, start_date, end_date)
                if r:
                    with connect() as conn4, conn4.cursor() as cur4:
                        # delete prior snapshot for this video (we want latest only by fetched_at)
                        for point in r:
                            cur4.execute(
                                """INSERT INTO video_retention
                                      (video_id, elapsed_pct, audience_watch_ratio,
                                       relative_retention_performance)
                                   VALUES (%s, %s, %s, %s)""",
                                (vid, point["elapsed_pct"], point["watch_ratio"], point["relative_perf"]),
                            )
                        conn4.commit()
                    total_retention += len(r)
            time.sleep(0.1)  # be polite

    print(f"\n=== synced {total_summary} summaries + {total_retention} retention points ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
