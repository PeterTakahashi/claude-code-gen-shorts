#!/usr/bin/env python3
"""Obtain per-channel YouTube OAuth tokens via the interactive consent flow.

For each channel registered in the DB (filter: id LIKE 'baltoon_%_news_ja' by
default, override via argv), this runs the InstalledAppFlow with
prompt='select_account' so the user must explicitly pick that channel's Brand
Account in the chooser. After the flow, channels.list(mine=true) is called and
the returned channel id is verified against the expected youtube_channel_id;
the token is saved ONLY on match. Mismatch = user picked the wrong Brand
Account; re-run for that channel.

Idempotent: channels with an existing valid token already pointing at the
expected channel are skipped.

Run:  PYTHONUNBUFFERED=1 .venv/bin/python tools/yt_oauth_setup.py
      PYTHONUNBUFFERED=1 .venv/bin/python tools/yt_oauth_setup.py baltoon_stocks_news_ja
"""
import socketserver
import sys
import time
import wsgiref.simple_server
from pathlib import Path

# Allow rapid reuse of port 8080 across the 5 sequential OAuth flows.
# allow_reuse_address (SO_REUSEADDR) alone is not enough on macOS — the previous
# server's socket lingers in TIME_WAIT and rebind still fails. SO_REUSEPORT
# (allow_reuse_port) lets the next bind succeed regardless. Set both on the
# wsgiref WSGIServer class that google-auth-oauthlib uses.
socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer.allow_reuse_port = True
wsgiref.simple_server.WSGIServer.allow_reuse_address = True
wsgiref.simple_server.WSGIServer.allow_reuse_port = True

ROOT = Path("/Users/apple/dev/claude-code/webtoon-gen")
sys.path.insert(0, str(ROOT))

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.db import connect

CLIENT_SECRET = ROOT / "client_secret_469186164436-1lul6dbdi3t42hn6sm7caud1bh0ss1sn.apps.googleusercontent.com.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
PORT = 8080  # client_secret has only localhost:8080/ as redirect URI


def fetch_targets(filter_ids):
    with connect() as c:
        if filter_ids:
            cur = c.execute(
                "SELECT id, display_name, youtube_channel_id, oauth_token_file "
                "FROM channels WHERE id = ANY(%s)",
                (filter_ids,),
            )
        else:
            cur = c.execute(
                "SELECT id, display_name, youtube_channel_id, oauth_token_file "
                "FROM channels WHERE id LIKE 'baltoon_%%_news_ja'"
            )
        return cur.fetchall()


def existing_channel_for(token_path: Path):
    """Return the channel id the token currently authorizes, or None."""
    if not token_path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = yt.channels().list(part="id", mine=True).execute().get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        print(f"  (token check failed: {str(e)[:120]})", flush=True)
        return None


def run_flow(token_path: Path, expected_uc: str, display: str) -> bool:
    print(f"\n>>> {display}", flush=True)
    print(f"    expected UC: {expected_uc}", flush=True)
    print(f"    A browser tab will open. **Select THIS channel's Brand Account** in the chooser.", flush=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=PORT, prompt="select_account", open_browser=True)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = yt.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    if not items:
        print("  !! channels.list returned nothing; token not saved.", flush=True)
        return False
    got = items[0]["id"]
    title = items[0]["snippet"]["title"]
    if got != expected_uc:
        print(f"  !! WRONG Brand Account picked. got UC={got} ({title}); expected {expected_uc}.", flush=True)
        print(f"     Token NOT saved. Re-run for: {token_path.name}", flush=True)
        return False
    token_path.write_text(creds.to_json())
    print(f"  ✓ saved {token_path.name}  ({title})", flush=True)
    return True


def main() -> int:
    filter_ids = sys.argv[1:] or None
    targets = fetch_targets(filter_ids)
    if not targets:
        print("no channels matched")
        return 1
    print(f"=== OAuth setup for {len(targets)} channel(s) ===", flush=True)
    n_ok = n_skip = n_fail = 0
    first_run = True
    for cid, disp, uc, token_file in targets:
        token_path = ROOT / token_file
        existing = existing_channel_for(token_path)
        if existing == uc:
            print(f"  ✓ {cid:30} already valid for {uc}, skip", flush=True); n_skip += 1; continue
        if existing and existing != uc:
            print(f"  ⚠ {cid}: existing token is for {existing}; will overwrite", flush=True)
            token_path.unlink(missing_ok=True)
        if not first_run:
            time.sleep(3)  # let the previous server's socket fully release
        first_run = False
        if run_flow(token_path, uc, disp):
            n_ok += 1
        else:
            n_fail += 1
    print(f"\nsummary: ok={n_ok}  skipped={n_skip}  failed={n_fail}", flush=True)
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
