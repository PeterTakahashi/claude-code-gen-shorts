"""Fetch extra YouTube Analytics dimensions per active video.

Three report types (all lifetime, per video):
  1. **traffic sources** (insightTrafficSourceType) → video_traffic_sources
     How views are acquired: SHORTS feed, BROWSE, SUGGESTED, YT_SEARCH, EXT_URL...
  2. **geography** (country)                          → video_geography
     Top countries by views — tests the JP-relevance hypothesis.
  3. **engagement** (shares/subs/playlist adds/etc.)  → video_engagement

Complements src.youtube_analytics_sync (summary + retention).
Requires the `yt-analytics.readonly` scope (already on all channel tokens).

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_analytics_extra
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_analytics_extra --channel ijinden_ja
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET


def _list_channels(conn, only_channel: str | None) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        sql = "SELECT id, oauth_token_file FROM channels WHERE oauth_token_file IS NOT NULL"
        params: tuple = ()
        if only_channel:
            sql += " AND id = %s"
            params = (only_channel,)
        cur.execute(sql, params)
        return cur.fetchall()


def _videos_on_channel(conn, channel_id: str, days_back: int) -> list[tuple[str, str]]:
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


def _query(analytics, *, metrics, start, end, video_id, dimensions=None, sort=None, max_results=None):
    kwargs = dict(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics=metrics,
        filters=f"video=={video_id}",
    )
    if dimensions:
        kwargs["dimensions"] = dimensions
    if sort:
        kwargs["sort"] = sort
    if max_results:
        kwargs["maxResults"] = max_results
    try:
        resp = analytics.reports().query(**kwargs).execute()
    except HttpError as e:
        print(f"  [{video_id}] {dimensions or 'totals'} failed: {str(e)[:120]}", file=sys.stderr)
        return None
    return resp


def fetch_traffic(analytics, video_id, start, end) -> list[dict] | None:
    resp = _query(analytics, metrics="views,estimatedMinutesWatched,averageViewPercentage",
                  start=start, end=end, video_id=video_id,
                  dimensions="insightTrafficSourceType", sort="-views")
    if not resp or not resp.get("rows"):
        return None
    return [{"source_type": r[0], "views": int(r[1]), "emw": float(r[2]), "avg_pct": float(r[3])}
            for r in resp["rows"]]


def fetch_geography(analytics, video_id, start, end) -> list[dict] | None:
    resp = _query(analytics, metrics="views,averageViewPercentage",
                  start=start, end=end, video_id=video_id,
                  dimensions="country", sort="-views", max_results=15)
    if not resp or not resp.get("rows"):
        return None
    return [{"country": r[0], "views": int(r[1]), "avg_pct": float(r[2])} for r in resp["rows"]]


def fetch_engagement(analytics, video_id, start, end) -> dict | None:
    resp = _query(analytics,
                  metrics="shares,subscribersGained,subscribersLost,videosAddedToPlaylists,likes,dislikes,comments",
                  start=start, end=end, video_id=video_id)
    if not resp or not resp.get("rows"):
        return None
    cols = [c["name"] for c in resp.get("columnHeaders", [])]
    return dict(zip(cols, resp["rows"][0]))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channel", default=None)
    p.add_argument("--days-back", type=int, default=60)
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=args.days_back)).isoformat()

    with connect() as conn:
        channels = _list_channels(conn, args.channel)

    n_traffic = n_geo = n_eng = 0
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
            videos = _videos_on_channel(conn2, ch_id, args.days_back)
        print(f"\n[{ch_id}]  {len(videos)} videos")

        for vid, title in videos:
            traffic = fetch_traffic(analytics, vid, start, end)
            geo = fetch_geography(analytics, vid, start, end)
            eng = fetch_engagement(analytics, vid, start, end)

            with connect() as conn3, conn3.cursor() as cur:
                if traffic:
                    for t in traffic:
                        cur.execute(
                            """INSERT INTO video_traffic_sources
                                  (video_id, source_type, views, est_minutes_watched, avg_view_pct)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (vid, t["source_type"], t["views"], t["emw"], t["avg_pct"]))
                    n_traffic += 1
                if geo:
                    for g in geo:
                        cur.execute(
                            """INSERT INTO video_geography (video_id, country, views, avg_view_pct)
                               VALUES (%s,%s,%s,%s)""",
                            (vid, g["country"], g["views"], g["avg_pct"]))
                    n_geo += 1
                if eng:
                    cur.execute(
                        """INSERT INTO video_engagement
                              (video_id, shares, subscribers_gained, subscribers_lost,
                               playlist_adds, likes, dislikes, comments)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (vid, int(eng.get("shares") or 0), int(eng.get("subscribersGained") or 0),
                         int(eng.get("subscribersLost") or 0), int(eng.get("videosAddedToPlaylists") or 0),
                         int(eng.get("likes") or 0), int(eng.get("dislikes") or 0),
                         int(eng.get("comments") or 0)))
                    n_eng += 1
                conn3.commit()

            top_src = traffic[0]["source_type"] if traffic else "-"
            top_country = geo[0]["country"] if geo else "-"
            shares = int(eng.get("shares") or 0) if eng else 0
            subs = int(eng.get("subscribersGained") or 0) if eng else 0
            print(f"  [{vid}] src={top_src} country={top_country} shares={shares} subs+={subs}  {title[:28]}")
            time.sleep(0.1)

    print(f"\n=== {n_traffic} traffic + {n_geo} geo + {n_eng} engagement videos synced ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
