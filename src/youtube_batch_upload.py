"""Batch-upload all chapters of a project to YouTube.

Reads upload_metadata.json under projects/<project_id>/ and uploads each chapter's
master.mp4 (or alternative video_filename) with title/description/tags + thumbnail.

Logs successful uploads to .youtube_uploads.json under the project dir so the
batch can resume after interruption — chapters already in the log get skipped.

Usage:
  uv run python -m src.youtube_batch_upload <project_id> [--privacy private|unlisted|public] [--force]

  --force   re-upload chapters that are already in the log
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .project import load
from .youtube_upload import upload, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN, resolve_channel_token


def _load_log(log_path: Path) -> dict:
    if log_path.exists():
        return json.loads(log_path.read_text(encoding="utf-8"))
    return {"uploads": {}}


def _save_log(log_path: Path, data: dict) -> None:
    log_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default=None)
    p.add_argument("--force", action="store_true", help="Re-upload chapters already in the log")
    p.add_argument("--channel", default=None,
                   help="channel_id (e.g. 'ijinden_ja', 'baltoon_biography_en') — resolves OAuth token from DB")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=None,
                   help="Explicit token path (overrides --channel)")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    if args.token is None:
        args.token = resolve_channel_token(args.channel)
    if args.channel:
        print(f"  channel    : {args.channel}  (token: {args.token.name})")

    project = load(args.project_id)
    project_dir = project.project_dir
    metadata_path = project_dir / "upload_metadata.json"
    if not metadata_path.exists():
        print(f"ERROR: missing {metadata_path}", file=sys.stderr)
        return 1
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    log_path = project_dir / ".youtube_uploads.json"
    log = _load_log(log_path)

    privacy = args.privacy or metadata.get("default_privacy", "private")
    default_tags = metadata.get("default_tags", "")
    footer = metadata.get("common_description_footer", "")

    chapters = metadata.get("chapters", [])
    print(f"=== batch upload: {args.project_id}  {len(chapters)} chapters  privacy={privacy} ===")

    for idx, ch in enumerate(chapters, start=1):
        ch_id = ch["id"]
        title = ch["title"]
        body = ch["description"] + footer
        tags_str = ch.get("tags", default_tags)
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]

        chapter = project.chapter(ch_id)
        video_filename = ch.get("video_filename", "master.mp4")
        video_path = chapter.output_dir / video_filename
        thumb_path = chapter.output_dir / "thumbnail.png"

        existing = log["uploads"].get(ch_id)
        if existing and existing.get("video_id") and not args.force:
            print(f"\n[{idx}/{len(chapters)}] {ch_id} — already uploaded as {existing.get('video_id')}, skipping")
            continue
        if existing and not existing.get("video_id"):
            print(f"\n[{idx}/{len(chapters)}] {ch_id} — previous attempt failed ({existing.get('error', '')[:60]}), retrying")

        if not video_path.exists():
            print(f"\n[{idx}/{len(chapters)}] {ch_id} — MISSING VIDEO {video_path}, skipping")
            log["uploads"][ch_id] = {"error": f"missing video {video_path}", "ts": datetime.utcnow().isoformat()}
            _save_log(log_path, log)
            continue

        print(f"\n[{idx}/{len(chapters)}] uploading {ch_id}: {title}")
        print(f"  video : {video_path}  ({video_path.stat().st_size/1024/1024:.1f} MiB)")
        if thumb_path.exists():
            print(f"  thumb : {thumb_path}")

        started = time.time()
        try:
            resp = upload(
                video_path=video_path,
                title=title,
                description=body,
                privacy=privacy,
                category_id="22",
                tags=tags,
                client_secret_path=args.client_secret,
                token_path=args.token,
                port=args.port,
                thumbnail_path=thumb_path if thumb_path.exists() else None,
            )
        except Exception as e:
            elapsed = time.time() - started
            print(f"  ERROR after {elapsed:.1f}s: {e}", file=sys.stderr)
            log["uploads"][ch_id] = {"error": str(e), "ts": datetime.utcnow().isoformat()}
            _save_log(log_path, log)
            continue

        vid = resp.get("id")
        elapsed = time.time() - started
        print(f"  ✓ uploaded in {elapsed:.1f}s — video_id={vid}")
        log["uploads"][ch_id] = {
            "video_id": vid,
            "title": title,
            "ts": datetime.utcnow().isoformat(),
            "url_studio": f"https://studio.youtube.com/video/{vid}/edit" if vid else None,
        }
        _save_log(log_path, log)

    print(f"\n=== done. log at {log_path} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
