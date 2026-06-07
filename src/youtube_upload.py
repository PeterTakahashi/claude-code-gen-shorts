"""YouTube video upload helper.

Usage:
    .venv/bin/python -m src.youtube_upload \\
        --video projects/ningen_shikkaku/output/chapter_01/youtube_long.mp4 \\
        --title "test upload" --privacy private

Auth:
    First run opens a browser for OAuth (loopback). Token is cached at
    .youtube_token.json so subsequent runs are non-interactive.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLIENT_SECRET = ROOT / "client_secret_469186164436-1lul6dbdi3t42hn6sm7caud1bh0ss1sn.apps.googleusercontent.com.json"
DEFAULT_TOKEN = ROOT / ".youtube_token.json"


def resolve_channel_token(channel_id: str | None) -> Path:
    """Resolve which .youtube_token.*.json to use for a given channel.
    Returns the path. Falls back to DEFAULT_TOKEN if no channel given."""
    if not channel_id:
        return DEFAULT_TOKEN
    try:
        from .db import connect, get_channel_token  # local import to avoid hard DB dep
        with connect() as conn:
            token_file = get_channel_token(conn, channel_id)
    except Exception as e:
        print(f"WARN: cannot read channel '{channel_id}' from DB ({e}); using default token", file=sys.stderr)
        return DEFAULT_TOKEN
    if not token_file:
        print(f"WARN: channel '{channel_id}' has no oauth_token_file; using default", file=sys.stderr)
        return DEFAULT_TOKEN
    p = Path(token_file)
    if not p.is_absolute():
        p = ROOT / p
    return p


def get_credentials(client_secret_path: Path, token_path: Path, port: int) -> Credentials:
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        return creds
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=port, prompt="consent", open_browser=True)
    token_path.write_text(creds.to_json())
    return creds


def upload(
    video_path: Path,
    title: str,
    description: str,
    privacy: str,
    category_id: str,
    tags: list[str],
    client_secret_path: Path,
    token_path: Path,
    port: int,
    thumbnail_path: Path | None = None,
) -> dict:
    if not video_path.exists():
        raise FileNotFoundError(f"video not found: {video_path}")
    creds = get_credentials(client_secret_path, token_path, port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(
        str(video_path), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4"
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    last_pct = -1
    started = time.time()
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct != last_pct:
                    elapsed = time.time() - started
                    print(f"  uploaded {pct}%  ({elapsed:.1f}s elapsed)", flush=True)
                    last_pct = pct
        except HttpError as e:
            print(f"HTTP error during upload: {e}", file=sys.stderr)
            raise

    if thumbnail_path is not None:
        if not thumbnail_path.exists():
            print(f"WARN: thumbnail not found, skipping: {thumbnail_path}", file=sys.stderr)
        else:
            vid = response.get("id")
            if not vid:
                print("WARN: no video id returned, cannot set thumbnail", file=sys.stderr)
            else:
                print(f"  setting thumbnail: {thumbnail_path.name}", flush=True)
                # Use broad except — thumbnails over 2MB raise a non-HttpError ResumableUpload error
                # that would otherwise abort the whole upload after the video is already on YouTube.
                try:
                    mimetype = "image/jpeg" if thumbnail_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                    youtube.thumbnails().set(
                        videoId=vid,
                        media_body=MediaFileUpload(str(thumbnail_path), mimetype=mimetype),
                    ).execute()
                    print("  thumbnail set", flush=True)
                except Exception as e:
                    print(f"WARN: thumbnail set failed: {e}", file=sys.stderr)

    return response


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True, type=Path)
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    p.add_argument("--category", default="22", help="YouTube categoryId (22=People & Blogs)")
    p.add_argument("--tags", default="", help="Comma-separated tags")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    p.add_argument("--port", type=int, default=8080, help="Loopback port for OAuth callback")
    p.add_argument("--thumbnail", type=Path, default=None, help="Thumbnail image (1280x720 PNG/JPG recommended)")
    args = p.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    print(f"video       : {args.video}")
    print(f"size        : {args.video.stat().st_size / 1024 / 1024:.1f} MiB")
    print(f"title       : {args.title}")
    print(f"privacy     : {args.privacy}")
    print(f"client_sec  : {args.client_secret}")
    print(f"token cache : {args.token}")
    print("---")

    resp = upload(
        video_path=args.video,
        title=args.title,
        description=args.description,
        privacy=args.privacy,
        category_id=args.category,
        tags=tags,
        client_secret_path=args.client_secret,
        token_path=args.token,
        port=args.port,
        thumbnail_path=args.thumbnail,
    )
    vid = resp.get("id")
    print("---")
    print(json.dumps(resp, indent=2, ensure_ascii=False))
    if vid:
        print(f"\nSUCCESS  video id: {vid}")
        print(f"URL (private): https://studio.youtube.com/video/{vid}/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
