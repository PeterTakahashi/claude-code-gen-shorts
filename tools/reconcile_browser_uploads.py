#!/usr/bin/env python3
"""Reconcile browser-uploaded shorts into the DB videos table.

The Playwright uploader's early scraper logged wrong video ids (dashboard links),
and browser uploads don't write the DB anyway. This finds each short's REAL video
id by matching its yaml title against the channel's live uploads (Data API), then
upserts a videos row so stats_sync / Redash track it.

Run: PYTHONPATH=. .venv/bin/python tools/reconcile_browser_uploads.py
"""
import os
import yaml
from googleapiclient.discovery import build

from src.db import connect, upsert_video
from src.youtube_upload import DEFAULT_CLIENT_SECRET, get_credentials, resolve_channel_token

# (project, short_id, channel_db_id)
ITEMS = [
    ("sports_legends", "sports-oh-868",              "baltoon_sports_legends_ja"),
    ("corporate_fall", "corpfall-nokia",             "baltoon_corporate_fall_ja"),
    ("animals",        "animals-otter-handholding",  "baltoon_animals_ja"),
    ("animals",        "animals-platypus",           "baltoon_animals_ja"),
    ("astronomy",      "astro-saturn-rings-vanish",  "baltoon_astronomy_ja"),
    ("astronomy",      "astro-betelgeuse-supernova", "baltoon_astronomy_ja"),
]


def channel_videos(channel_db_id):
    """Return {title: (video_id, privacy)} for the channel's recent uploads."""
    creds = get_credentials(DEFAULT_CLIENT_SECRET, resolve_channel_token(channel_db_id), port=8091)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    uploads = yt.channels().list(part="contentDetails", mine=True).execute()[
        "items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    out, page = {}, None
    while True:
        r = yt.playlistItems().list(part="snippet,contentDetails", playlistId=uploads,
                                    maxResults=50, pageToken=page).execute()
        for it in r.get("items", []):
            out[it["snippet"]["title"].strip()] = it["contentDetails"]["videoId"]
        page = r.get("nextPageToken")
        if not page:
            break
    return out


def short_title(proj, sid):
    d = yaml.safe_load(open(f"projects/{proj}/shorts/{sid}.yaml", encoding="utf-8"))
    ja = d.get("ja", {}) if isinstance(d.get("ja"), dict) else {}
    return (ja.get("title") or d.get("title") or "").strip(), \
           (ja.get("description") or d.get("description") or "")


def main() -> int:
    cache = {}
    have_series = None
    with connect() as c:
        have_series = {r[0] for r in c.execute("select id from series").fetchall()}
        for proj, sid, chan in ITEMS:
            title, desc = short_title(proj, sid)
            if chan not in cache:
                cache[chan] = channel_videos(chan)
            vid = cache[chan].get(title)
            if not vid:
                print(f"  !! NO MATCH  {proj}/{sid}  title={title!r}")
                continue
            mp4 = f"projects/{proj}/output/shorts/{sid}/ja/short.mp4"
            fsize = os.path.getsize(mp4) if os.path.isfile(mp4) else None
            upsert_video(c, video_id=vid, series_id=(proj if proj in have_series else None),
                         kind="short", title=title, description=desc, privacy="public",
                         file_size_bytes=fsize,
                         master_mp4_path=mp4 if os.path.isfile(mp4) else None, channel_id=chan)
            print(f"  registered {vid}  {proj}/{sid} -> {chan}  | {title}")
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
