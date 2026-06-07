#!/usr/bin/env python3
"""List a channel's recent uploads (video_id, title, privacy) via the Data API.

Read-only (cheap quota). Used to find duplicate/old uploads and recover real
video ids when the Studio browser-uploader logged the wrong id.

Usage:
  .venv/bin/python tools/yt_list_channel.py <channel_db_id> [title_substring] [max]
  e.g. .venv/bin/python tools/yt_list_channel.py ijinden_ja 柳井 40
"""
import sys
from googleapiclient.discovery import build

from src.youtube_upload import (DEFAULT_CLIENT_SECRET, get_credentials,
                                resolve_channel_token)


def main() -> int:
    channel_id = sys.argv[1]
    needle = sys.argv[2] if len(sys.argv) > 2 else ""
    maxn = int(sys.argv[3]) if len(sys.argv) > 3 else 40

    token = resolve_channel_token(channel_id)
    creds = get_credentials(DEFAULT_CLIENT_SECRET, token, port=8090)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ch = yt.channels().list(part="contentDetails,snippet", mine=True).execute()
    item = ch["items"][0]
    uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"channel: {item['snippet']['title']}  uploads_playlist={uploads}", flush=True)

    vids = []
    page = None
    while len(vids) < maxn:
        r = yt.playlistItems().list(part="snippet,contentDetails", playlistId=uploads,
                                    maxResults=50, pageToken=page).execute()
        for it in r.get("items", []):
            vids.append((it["contentDetails"]["videoId"], it["snippet"]["title"]))
        page = r.get("nextPageToken")
        if not page:
            break

    # fetch privacy status in batches of 50
    status = {}
    for i in range(0, len(vids), 50):
        ids = [v for v, _ in vids[i:i + 50]]
        rs = yt.videos().list(part="status", id=",".join(ids)).execute()
        for it in rs.get("items", []):
            status[it["id"]] = it["status"]["privacyStatus"]

    print(f"--- {len(vids)} recent uploads" + (f" matching {needle!r}" if needle else "") + " ---", flush=True)
    n = 0
    for vid, title in vids:
        if needle and needle not in title:
            continue
        n += 1
        print(f"  {vid}  [{status.get(vid,'?'):8}]  {title}", flush=True)
    print(f"({n} shown)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
