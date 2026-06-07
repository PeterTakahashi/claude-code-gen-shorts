"""Create / update YouTube playlists from videos in the DB.

For each project (series) we create one playlist and add every long-form video
(in chapter order). Shorts are skipped by default — they live in their own
optional shorts playlist.

The playlist id is stored back in the `series.metadata` JSON column so future
runs can update the same playlist instead of creating a new one.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_playlist <series_id> [<series_id> …]
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_playlist stevejobs elonmusk
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_playlist all
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_playlist stevejobs --privacy public
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_playlist stevejobs --kind short

Scopes needed: youtube.upload covers playlist creation + item insertion.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN

# Stable, fixed chapter order. main goes first (the elonmusk "main" alias = ch1).
CHAPTER_ORDER = [
    "main",  # elonmusk alias for ch1
    "ch1", "ch2", "ch3", "ch4", "ch5", "ch6",
    "ch7", "ch8", "ch9", "ch10", "ch11", "ch12",
]


def _sort_key(ch_id: str) -> int:
    try:
        return CHAPTER_ORDER.index(ch_id)
    except ValueError:
        return 999


def _series_row(conn, series_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title_ja, subject, series_short, metadata FROM series WHERE id = %s",
            (series_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def _videos_for_series(conn, series_id: str, kind: str = "long") -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT video_id, chapter_id, title
            FROM videos
            WHERE series_id = %s AND kind = %s AND superseded_by IS NULL
            """,
            (series_id, kind),
        )
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    rows.sort(key=lambda r: _sort_key(r["chapter_id"] or ""))
    return rows


def _store_playlist_id(conn, series_id: str, key: str, playlist_id: str) -> None:
    """Persist playlist_id under series.metadata['playlists'][<key>]."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE series
            SET metadata = COALESCE(metadata, '{}'::jsonb)
                || jsonb_build_object('playlists', jsonb_build_object(%s::text, %s::text))
            WHERE id = %s
            """,
            (key, playlist_id, series_id),
        )


def _get_stored_playlist_id(series_row: dict, key: str) -> str | None:
    meta = series_row.get("metadata") or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    return ((meta.get("playlists") or {}).get(key)) if meta else None


def ensure_playlist(youtube, *, title: str, description: str, privacy: str) -> str:
    """Create a new playlist and return its id."""
    body = {
        "snippet": {"title": title, "description": description, "defaultLanguage": "ja"},
        "status": {"privacyStatus": privacy},
    }
    resp = youtube.playlists().insert(part="snippet,status", body=body).execute()
    return resp["id"]


def existing_items(youtube, playlist_id: str) -> dict[str, str]:
    """Return {video_id: playlistItemId} for items already in the playlist."""
    out: dict[str, str] = {}
    page_token = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in resp.get("items", []):
            out[item["contentDetails"]["videoId"]] = item["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def add_to_playlist(youtube, playlist_id: str, video_id: str, position: int | None = None) -> None:
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }
    }
    if position is not None:
        body["snippet"]["position"] = position
    youtube.playlistItems().insert(part="snippet", body=body).execute()


def sync_series_playlist(
    youtube,
    series_id: str,
    *,
    kind: str = "long",
    privacy: str = "public",
    dry_run: bool = False,
) -> str | None:
    with connect() as conn:
        s = _series_row(conn, series_id)
        if not s:
            print(f"  {series_id}: not in DB — run db_import first", file=sys.stderr)
            return None
        videos = _videos_for_series(conn, series_id, kind=kind)
        if not videos:
            print(f"  {series_id}: no {kind} videos found")
            return None

        title_ja = s["title_ja"]
        playlist_title = f"{title_ja}" if kind == "long" else f"{title_ja} Shorts"
        playlist_desc = (
            f"{title_ja} の全エピソード。"
            if kind == "long"
            else f"{title_ja} の Shorts。長尺版は同名プレイリストで。"
        )
        key = "long" if kind == "long" else "shorts"
        existing_id = _get_stored_playlist_id(s, key)

        if existing_id and not dry_run:
            print(f"  reusing playlist {existing_id}")
            playlist_id = existing_id
        elif dry_run:
            print(f"  [dry-run] would create playlist '{playlist_title}' with {len(videos)} videos")
            return None
        else:
            playlist_id = ensure_playlist(
                youtube, title=playlist_title, description=playlist_desc, privacy=privacy,
            )
            _store_playlist_id(conn, series_id, key, playlist_id)
            conn.commit()
            print(f"  created playlist {playlist_id}: {playlist_title}")

        already = existing_items(youtube, playlist_id) if existing_id else {}
        added = 0
        for i, v in enumerate(videos):
            if v["video_id"] in already:
                print(f"    [{i+1}/{len(videos)}] {v['video_id']}  {v['chapter_id']}  (already in playlist)")
                continue
            try:
                add_to_playlist(youtube, playlist_id, v["video_id"], position=i)
                print(f"    [{i+1}/{len(videos)}] {v['video_id']}  {v['chapter_id']}  ✓ added")
                added += 1
            except HttpError as e:
                print(f"    [{i+1}/{len(videos)}] {v['video_id']}  {v['chapter_id']}  ✗ {e}", file=sys.stderr)

        print(f"  → {added} new items added to {playlist_id}")
        return playlist_id


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("series_ids", nargs="+", help="series ids (or 'all')")
    p.add_argument("--kind", choices=["long", "short"], default="long")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="public",
                   help="Default 'public' — easier to share. Override for unlisted/private.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    creds = get_credentials(args.client_secret, args.token, args.port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    if args.series_ids == ["all"]:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM series ORDER BY id")
                series_ids = [r[0] for r in cur.fetchall()]
    else:
        series_ids = args.series_ids

    print(f"playlists for: {', '.join(series_ids)}  kind={args.kind}  privacy={args.privacy}\n")
    for sid in series_ids:
        print(f"=== {sid} ===")
        sync_series_playlist(
            youtube, sid, kind=args.kind, privacy=args.privacy, dry_run=args.dry_run,
        )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
