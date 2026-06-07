"""Set a custom thumbnail on a YouTube playlist.

YouTube Data API v3 supports `playlistImages.insert` (relatively new endpoint)
which uploads a custom image as the playlist thumbnail. **This often fails with
403** on accounts that haven't been verified for custom thumbnails (phone
verification required for the channel).

If the API call fails, the playlist will continue to show an auto-generated
thumbnail from one of its videos.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_playlist_thumbnail <series_id> [<image_path>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN


def _playlist_id_for(series_id: str) -> str | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT metadata->'playlists'->>'long' FROM series WHERE id = %s",
                (series_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def _default_thumbnail(series_id: str) -> Path:
    """Use chapter-1 thumbnail of the series as the playlist thumbnail."""
    proj = Path(__file__).resolve().parent.parent / "projects" / series_id / "output"
    candidates = [
        proj / "ch1" / "thumbnail.png",
        proj / "main" / "thumbnail.png",  # elonmusk uses 'main' alias for ch1
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"no chapter-1 thumbnail found under {proj}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("series_id")
    p.add_argument("image", type=Path, nargs="?", default=None,
                   help="Custom thumbnail image (default: ch1 thumbnail of the series)")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    playlist_id = _playlist_id_for(args.series_id)
    if not playlist_id:
        print(f"ERROR: no playlist registered for series '{args.series_id}'", file=sys.stderr)
        return 1
    image = args.image or _default_thumbnail(args.series_id)

    creds = get_credentials(args.client_secret, args.token, args.port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    print(f"playlist : {playlist_id}")
    print(f"image    : {image}")

    try:
        # Newer API: playlistImages.insert  (uses media upload).
        # Body must contain snippet.playlistId + type='playlistCustomThumbnail'.
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "type": "playlistCustomThumbnail",
            }
        }
        req = youtube.playlistImages().insert(
            part="snippet",
            body=body,
            media_body=MediaFileUpload(str(image), mimetype="image/png", resumable=False),
        )
        resp = req.execute()
        print("✓ playlist thumbnail set")
        print(resp)
    except AttributeError:
        print("WARN: the installed google-api-python-client does not expose playlistImages."
              " Upgrade with `uv sync`, or set thumbnail manually via YouTube Studio.",
              file=sys.stderr)
        return 2
    except HttpError as e:
        print(f"WARN: playlist thumbnail API rejected the request: {e}", file=sys.stderr)
        print("  → Likely the account is not verified for custom thumbnails (phone verification).")
        print("  → Workaround: in YouTube Studio, open the playlist and pick a video"
              " whose thumbnail you want to use as the playlist thumbnail.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
