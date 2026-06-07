"""Import existing .youtube_uploads.json files + upload_metadata.json into Postgres.

For each project under projects/ that has upload_metadata.json + .youtube_uploads.json,
insert a `series` row + one `videos` row per successfully-uploaded chapter.

Idempotent: re-running upserts the same data.

Usage:
  uv run python -m src.db_import                    # import everything
  uv run python -m src.db_import stevejobs elonmusk # import specific projects
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .db import connect, upsert_series, upsert_video

ROOT = Path(__file__).resolve().parent.parent


def _ffprobe_duration(path: Path) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def import_project(project_id: str) -> int:
    proj_dir = ROOT / "projects" / project_id
    meta_path = proj_dir / "upload_metadata.json"
    log_path = proj_dir / ".youtube_uploads.json"
    if not meta_path.exists():
        print(f"  {project_id}: no upload_metadata.json, skip")
        return 0
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"uploads": {}}

    series_id = project_id
    title_ja = metadata.get("series_name", project_id)
    subject = metadata.get("subject")
    series_short = metadata.get("series_short")
    default_tags = [t.strip() for t in metadata.get("default_tags", "").split(",") if t.strip()]
    footer = metadata.get("common_description_footer", "")

    chapters_by_id = {c["id"]: c for c in metadata.get("chapters", [])}

    with connect() as conn:
        upsert_series(
            conn,
            series_id=series_id,
            title_ja=title_ja,
            subject=subject,
            series_short=series_short,
            metadata={"default_privacy": metadata.get("default_privacy")},
        )

        n_inserted = 0
        for ch_id, entry in log.get("uploads", {}).items():
            vid = entry.get("video_id")
            if not vid:
                # error entry without video_id — skip
                continue
            ch_meta = chapters_by_id.get(ch_id, {})
            video_filename = ch_meta.get("video_filename", "master.mp4")
            mp4_path = proj_dir / "output" / ch_id / video_filename
            thumb_path = proj_dir / "output" / ch_id / "thumbnail.png"
            duration = _ffprobe_duration(mp4_path) if mp4_path.exists() else None
            size = mp4_path.stat().st_size if mp4_path.exists() else None

            upsert_video(
                conn,
                video_id=vid,
                series_id=series_id,
                chapter_id=ch_id,
                kind="long",
                title=ch_meta.get("title", entry.get("title", ch_id)),
                description=(ch_meta.get("description", "") + footer) if ch_meta else None,
                tags=default_tags,
                privacy=metadata.get("default_privacy", "private"),
                duration_seconds=duration,
                file_size_bytes=size,
                master_mp4_path=str(mp4_path) if mp4_path.exists() else None,
                thumbnail_path=str(thumb_path) if thumb_path.exists() else None,
                metadata={"upload_ts": entry.get("ts"), "url_studio": entry.get("url_studio")},
            )
            n_inserted += 1
            print(f"  {project_id}/{ch_id}: {vid}  ({duration:.1f}s)" if duration else f"  {project_id}/{ch_id}: {vid}")
        conn.commit()
    return n_inserted


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("projects", nargs="*", help="Project ids to import (default: all)")
    args = p.parse_args()

    if args.projects:
        targets = args.projects
    else:
        targets = sorted(p.name for p in (ROOT / "projects").iterdir() if (p / "upload_metadata.json").exists())

    print(f"importing: {', '.join(targets)}")
    total = 0
    for pid in targets:
        n = import_project(pid)
        total += n
        print(f"  → {pid}: {n} videos\n")
    print(f"done. {total} videos in DB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
