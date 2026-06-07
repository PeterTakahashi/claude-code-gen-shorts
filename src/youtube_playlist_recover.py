"""Find orphan playlists that were created by youtube_playlist.py but not stored
in the DB (e.g. the first run crashed after API call but before commit).
Lists all my playlists; matches by title; records or deletes."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from googleapiclient.discovery import build

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--delete-extras", action="store_true",
                   help="Delete duplicate orphan playlists (keep one of each title)")
    args = p.parse_args()

    creds = get_credentials(DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN, 8080)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
    plists = resp.get("items", [])
    print(f"found {len(plists)} playlists on your channel:\n")

    titles: dict[str, list[str]] = {}
    for pl in plists:
        title = pl["snippet"]["title"]
        pid = pl["id"]
        titles.setdefault(title, []).append(pid)
        print(f"  {pid}  {title}  ({pl['snippet']['publishedAt']})")

    # Match my known series titles
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title_ja FROM series")
            series = {row[1]: row[0] for row in cur.fetchall()}

    print(f"\nknown series titles: {list(series.keys())}\n")

    for title, ids in titles.items():
        sid = series.get(title)
        if not sid:
            continue
        keep = ids[0]
        extras = ids[1:]
        print(f"  '{title}' → series='{sid}'  keep={keep}  extras={extras}")

        # Record the keep id
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE series
                    SET metadata = COALESCE(metadata, '{}'::jsonb)
                        || jsonb_build_object('playlists', jsonb_build_object('long'::text, %s::text))
                    WHERE id = %s
                    """,
                    (keep, sid),
                )
            conn.commit()
        print(f"    stored playlist_id={keep} into series.metadata for {sid}")

        if args.delete_extras and extras:
            for extra in extras:
                youtube.playlists().delete(id=extra).execute()
                print(f"    deleted duplicate playlist {extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
