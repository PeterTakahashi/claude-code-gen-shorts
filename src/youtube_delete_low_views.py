"""Delete low-view shorts from a channel, mark for later re-upload.

For each candidate video:
  1. youtube.videos().delete(id=video_id)        (50 quota units / call)
  2. Mark DB row with metadata.deleted_at + deleted_reason
     (superseded_by FK requires a real video_id, so we use the metadata jsonb instead)
  3. Remove the short's entry from projects/<series>/.youtube_shorts_uploads.json
     so the next youtube_batch_upload_shorts run will re-upload it.

Default criteria: channel='ijinden_ja', kind='short', view_count < 50,
uploaded > 24 hours ago. Override with --views-lt and --hours.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_delete_low_views \
      --channel ijinden_ja --dry-run

  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_delete_low_views \
      --channel ijinden_ja --views-lt 50 --hours 24
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, resolve_channel_token

ROOT = Path(__file__).resolve().parent.parent


def _strip_from_upload_log(series_id: str, short_id: str, language: str = "ja") -> bool:
    """Remove the upload log entry so the next upload run re-uploads.
    Returns True if an entry was removed."""
    log_path = ROOT / "projects" / series_id / ".youtube_shorts_uploads.json"
    if not log_path.exists():
        return False
    log = json.loads(log_path.read_text(encoding="utf-8"))
    # Log key: ja → bare sid; other → sid__lang
    key = short_id if language == "ja" else f"{short_id}__{language}"
    if key in log.get("uploads", {}):
        del log["uploads"][key]
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--kind", default="short")
    ap.add_argument("--views-lt", type=int, default=50)
    ap.add_argument("--hours", type=int, default=24, help="only delete videos older than this")
    ap.add_argument("--series", default=None)
    ap.add_argument("--language", default="ja",
                    help="language of the upload log entry to strip (ja default)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    ap.add_argument("--token", type=Path, default=None)
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    token = args.token or resolve_channel_token(args.channel)
    creds = get_credentials(args.client_secret, token, args.port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    deleted_at = datetime.utcnow().isoformat()
    reason = f"low_views_repost_{datetime.utcnow().strftime('%Y-%m-%d')}"

    with connect() as conn, conn.cursor() as cur:
        sql = """
            WITH latest AS (
              SELECT DISTINCT ON (video_id) video_id, view_count
              FROM video_stats ORDER BY video_id, fetched_at DESC
            )
            SELECT v.video_id, v.series_id, v.title, l.view_count
            FROM videos v JOIN latest l USING (video_id)
            WHERE v.channel_id = %s AND v.kind = %s AND v.superseded_by IS NULL
              AND l.view_count < %s
              AND v.uploaded_at < NOW() - (%s || ' hours')::interval
        """
        params: list = [args.channel, args.kind, args.views_lt, str(args.hours)]
        if args.series:
            sql += " AND v.series_id = %s"; params.append(args.series)
        sql += " ORDER BY l.view_count DESC, v.uploaded_at"
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        print(f"no candidates (channel={args.channel} views<{args.views_lt} age>{args.hours}h)")
        return 0

    print(f"=== {len(rows)} videos to delete  (channel={args.channel}, "
          f"views<{args.views_lt}, age>{args.hours}h, dry_run={args.dry_run}) ===")
    for vid, series_id, title, vc in rows:
        print(f"  [{vid}] views={vc:3d}  {series_id:18s}  {title[:48]}")
    print()

    if args.dry_run:
        return 0

    deleted = 0
    for vid, series_id, title, vc in rows:
        # short_id stored in metadata.short_id when uploaded; recover via DB
        with connect() as conn2, conn2.cursor() as cur2:
            cur2.execute(
                "SELECT metadata->>'short_id' FROM videos WHERE video_id = %s", (vid,)
            )
            sid_row = cur2.fetchone()
            short_id = sid_row[0] if sid_row and sid_row[0] else None

        try:
            youtube.videos().delete(id=vid).execute()
        except HttpError as e:
            # 404 = already gone (e.g. partial prior run); still update DB + log.
            if getattr(e, "resp", None) and e.resp.status == 404:
                print(f"  [{vid}] already gone from YouTube (404), continuing")
            else:
                print(f"  [{vid}] DELETE FAILED: {e}", file=sys.stderr)
                continue

        # DB: merge into metadata jsonb. superseded_by has an FK to videos(video_id),
        # so we cannot use it for a sentinel — store deletion info in metadata.
        with connect() as conn3, conn3.cursor() as cur3:
            cur3.execute(
                """UPDATE videos
                   SET metadata = COALESCE(metadata, '{}'::jsonb) ||
                                  jsonb_build_object('deleted_at', %s::text,
                                                     'deleted_reason', %s::text,
                                                     'previous_view_count', %s::bigint)
                   WHERE video_id = %s::text""",
                (deleted_at, reason, vc, vid),
            )
            conn3.commit()

        # Strip from upload log so re-upload works
        log_removed = False
        if short_id:
            log_removed = _strip_from_upload_log(series_id, short_id, args.language)

        deleted += 1
        print(f"  [{vid}] ✓ deleted (views={vc}) "
              f"short_id={short_id} log_stripped={log_removed}")
        time.sleep(0.15)

    print(f"\n=== deleted {deleted} / {len(rows)} ===")
    print(f"   marker: superseded_by = '{marker}'")
    print(f"   re-upload via:  PYTHONUNBUFFERED=1 .venv/bin/python -m "
          f"src.youtube_batch_upload_shorts <project_id> --channel {args.channel} "
          f"--language {args.language} --privacy public --only <short_id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
