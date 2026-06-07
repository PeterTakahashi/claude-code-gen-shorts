"""One-off: register ADB-app-uploaded shorts into the DB.

Shorts uploaded via the YouTube app (ADB flow) never hit upsert_video, so the
`videos` table doesn't know about them and stats sync skips them. This script
discovers each one by listing the channel's uploads playlist, matching by a
title keyword, then upserts kind='short' with the right channel/series.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m tools.register_adb_uploads
"""
from __future__ import annotations

from pathlib import Path

import yaml
from googleapiclient.discovery import build

from src.db import connect, upsert_video
from src.youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, resolve_channel_token

ROOT = Path(__file__).resolve().parent.parent

# (channel_id, project/series_id, short_id, title keyword to match)
TARGETS = [
    ("baltoon_animals_ja",        "animals",        "animals-immortal-jellyfish", "ベニクラゲ"),
    ("ijinden_ja",                "stevejobs",      "jobs-zen-kobun",             "禅僧"),
    ("baltoon_sports_legends_ja", "sports_legends", "sports-ohtani-trash",        "ゴミ"),
]


def recent_uploads(youtube, max_results: int = 15) -> list[dict]:
    ch = youtube.channels().list(part="contentDetails", mine=True).execute()
    uploads_pl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = youtube.playlistItems().list(
        part="snippet,contentDetails", playlistId=uploads_pl, maxResults=max_results
    ).execute().get("items", [])
    out = []
    for it in items:
        out.append({
            "video_id": it["contentDetails"]["videoId"],
            "title": it["snippet"]["title"],
            "published": it["contentDetails"].get("videoPublishedAt", ""),
        })
    return out


def main() -> int:
    with connect() as conn:
        for channel_id, project, short_id, keyword in TARGETS:
            token = resolve_channel_token(channel_id)
            creds = get_credentials(DEFAULT_CLIENT_SECRET, token, 8080)
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            uploads = recent_uploads(youtube)
            match = next((u for u in uploads if keyword in u["title"]), None)
            if not match:
                print(f"[{channel_id}] NO MATCH for '{keyword}'. Recent titles:")
                for u in uploads[:5]:
                    print(f"    {u['video_id']}  {u['title']}")
                continue

            ycfg = yaml.safe_load((ROOT / "projects" / project / "shorts" / f"{short_id}.yaml").read_text(encoding="utf-8"))
            ja = ycfg.get("ja", {})
            title = ja.get("title", match["title"])
            description = ja.get("description", "")
            out_dir = ROOT / "projects" / project / "output" / "shorts" / short_id / "ja"
            mp4 = out_dir / "short.mp4"
            thumb = out_dir / "thumbnail.jpg"

            upsert_video(
                conn,
                video_id=match["video_id"],
                series_id=project,
                kind="short",
                title=title,
                description=description,
                tags=["Shorts"],
                privacy="public",
                master_mp4_path=str(mp4) if mp4.exists() else None,
                thumbnail_path=str(thumb) if thumb.exists() else None,
                channel_id=channel_id,
                metadata={"short_id": short_id, "upload_method": "adb_app", "kaiju_bgm": True},
            )
            conn.commit()
            print(f"[{channel_id}] registered {match['video_id']}  {title}  (published {match['published']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
