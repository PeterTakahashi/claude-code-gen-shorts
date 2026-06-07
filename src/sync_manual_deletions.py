"""Mark manually-deleted videos in DB + strip upload log entries.

When the user deletes videos directly in YouTube Studio (no API call), our DB
still shows them as active. This script syncs state:

For each candidate video (same criteria as youtube_delete_low_views):
  1. Merge {deleted_at, deleted_reason, previous_view_count} into metadata jsonb
  2. Strip the short's entry from projects/<series>/.youtube_shorts_uploads.json
     so the next batch upload run will re-upload it.

No YouTube API calls — fast and no quota cost.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.sync_manual_deletions \
      --channel ijinden_ja --views-lt 50 --hours 24 --reason manual_delete
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .db import connect

ROOT = Path(__file__).resolve().parent.parent


def _strip_from_upload_log(series_id: str, short_id: str, language: str = "ja") -> bool:
    log_path = ROOT / "projects" / series_id / ".youtube_shorts_uploads.json"
    if not log_path.exists():
        return False
    log = json.loads(log_path.read_text(encoding="utf-8"))
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
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--series", default=None)
    ap.add_argument("--language", default="ja")
    ap.add_argument("--reason", default=None,
                    help="default: manual_delete_<YYYY-MM-DD>")
    args = ap.parse_args()

    deleted_at = datetime.utcnow().isoformat()
    reason = args.reason or f"manual_delete_{datetime.utcnow().strftime('%Y-%m-%d')}"

    with connect() as conn, conn.cursor() as cur:
        sql = """
            WITH latest AS (
              SELECT DISTINCT ON (video_id) video_id, view_count
              FROM video_stats ORDER BY video_id, fetched_at DESC
            )
            SELECT v.video_id, v.series_id, v.title, l.view_count,
                   v.metadata->>'short_id' AS short_id,
                   v.metadata->>'deleted_at' AS already_deleted
            FROM videos v JOIN latest l USING (video_id)
            WHERE v.channel_id = %s AND v.kind = %s AND v.superseded_by IS NULL
              AND l.view_count < %s
              AND v.uploaded_at < NOW() - (%s || ' hours')::interval
        """
        params: list = [args.channel, args.kind, args.views_lt, str(args.hours)]
        if args.series:
            sql += " AND v.series_id = %s"; params.append(args.series)
        sql += " ORDER BY l.view_count, v.uploaded_at"
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        print("no rows match")
        return 0

    updated = 0
    skipped_already = 0
    for vid, series_id, title, vc, sid, already in rows:
        if already:
            skipped_already += 1
            continue
        with connect() as conn2, conn2.cursor() as cur2:
            cur2.execute(
                """UPDATE videos
                   SET metadata = COALESCE(metadata, '{}'::jsonb) ||
                                  jsonb_build_object('deleted_at', %s::text,
                                                     'deleted_reason', %s::text,
                                                     'previous_view_count', %s::bigint)
                   WHERE video_id = %s::text""",
                (deleted_at, reason, vc, vid),
            )
            conn2.commit()
        log_removed = _strip_from_upload_log(series_id, sid, args.language) if sid else False
        updated += 1
        print(f"  [{vid}] views={vc:3d} {series_id:18s} {(sid or '?'):40s} log_stripped={log_removed}")

    print(f"\n=== marked {updated} (already marked: {skipped_already}) / {len(rows)} ===")
    print(f"    reason: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
