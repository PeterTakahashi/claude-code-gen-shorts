"""Delete a YouTube video by ID.

Usage:
    PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_delete --video-id <ID>

Requires the youtube.force-ssl scope (separate from upload scope), so the first
run opens a fresh OAuth flow. Token cached at .youtube_token_manage.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLIENT_SECRET = ROOT / "client_secret_469186164436-1lul6dbdi3t42hn6sm7caud1bh0ss1sn.apps.googleusercontent.com.json"
DEFAULT_TOKEN = ROOT / ".youtube_token_manage.json"


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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--video-id", required=True)
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    creds = get_credentials(args.client_secret, args.token, args.port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        resp = youtube.videos().delete(id=args.video_id).execute()
    except HttpError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return 1
    print(f"DELETED video id: {args.video_id}")
    if resp:
        print(resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
