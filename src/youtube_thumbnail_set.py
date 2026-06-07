"""Set a thumbnail on an already-uploaded YouTube video.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_thumbnail_set <video_id> <image_path>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN


def set_thumbnail(video_id: str, image_path: Path,
                  client_secret: Path = DEFAULT_CLIENT_SECRET,
                  token: Path = DEFAULT_TOKEN, port: int = 8080) -> bool:
    creds = get_credentials(client_secret, token, port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    mimetype = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(image_path), mimetype=mimetype),
        ).execute()
        print(f"  ✓ {video_id} thumbnail set ({image_path.stat().st_size//1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ {video_id} {e}", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("image_path", type=Path)
    args = p.parse_args()
    return 0 if set_thumbnail(args.video_id, args.image_path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
