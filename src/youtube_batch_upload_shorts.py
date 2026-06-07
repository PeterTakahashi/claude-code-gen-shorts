"""Batch-upload all generated shorts under projects/<id>/shorts/*.yaml to YouTube.

For each short:
  1. read `projects/<id>/shorts/<short_id>.yaml`
  2. find `projects/<id>/output/shorts/<short_id>/short.mp4` (and thumbnail.png)
  3. look up the parent chapter's long-form video_id from the DB (for linking)
  4. youtube videos.insert with title/description from the yaml + #Shorts tag
  5. upsert into `videos` table with kind='short', parent_video_id=<long-form id>

Resumable via `projects/<id>/.youtube_shorts_uploads.json`.

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_batch_upload_shorts <project_id>
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_batch_upload_shorts <project_id> --privacy public
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from .db import connect, upsert_video
from .youtube_upload import upload, DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN, resolve_channel_token

ROOT = Path(__file__).resolve().parent.parent


def _load_log(p: Path) -> dict:
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"uploads": {}}


def _save_log(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _parent_video_id(conn, project_id: str, parent_chapter: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT video_id FROM videos
            WHERE series_id = %s AND chapter_id = %s
              AND kind = 'long' AND superseded_by IS NULL
            ORDER BY uploaded_at DESC LIMIT 1
            """,
            (project_id, parent_chapter),
        )
        row = cur.fetchone()
        return row[0] if row else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    p.add_argument("--force", action="store_true")
    p.add_argument("--only", default=None, help="comma-separated short_ids to upload")
    p.add_argument("--channel", default=None,
                   help="channel_id from channels table (e.g. 'ijinden_ja', 'baltoon_biography_en'). "
                        "Resolves to the channel's OAuth token file automatically.")
    p.add_argument("--language", default="ja",
                   help="Source language to upload. ja → output/shorts/<sid>/short.mp4. "
                        "Non-ja → output/shorts/<sid>/<lang>/short.mp4 (requires that build).")
    p.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    p.add_argument("--token", type=Path, default=None,
                   help="Explicit token file path (overrides --channel)")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    # Resolve which OAuth token to use:
    # 1. --token explicit path (highest priority)
    # 2. --channel → DB lookup
    # 3. fall back to DEFAULT_TOKEN
    if args.token is None:
        args.token = resolve_channel_token(args.channel)
    if args.channel:
        print(f"  channel    : {args.channel}  (token: {args.token.name})")
    else:
        print(f"  token      : {args.token.name}")

    project_dir = ROOT / "projects" / args.project_id
    shorts_dir = project_dir / "shorts"
    if not shorts_dir.exists():
        print(f"ERROR: no shorts dir at {shorts_dir}", file=sys.stderr)
        return 1
    short_yamls = sorted(shorts_dir.glob("*.yaml"))

    if args.only:
        only = {s.strip() for s in args.only.split(",")}
        short_yamls = [y for y in short_yamls if y.stem in only]

    log_path = project_dir / ".youtube_shorts_uploads.json"
    log = _load_log(log_path)

    print(f"=== shorts upload: {args.project_id}  {len(short_yamls)} shorts  privacy={args.privacy} ===")

    with connect() as conn:
        for idx, yml in enumerate(short_yamls, start=1):
            cfg = yaml.safe_load(yml.read_text(encoding="utf-8"))
            sid = cfg["id"]
            # Language is always in its own subfolder
            short_out = project_dir / "output" / "shorts" / sid / args.language
            video_mp4 = short_out / "short.mp4"
            # Prefer JPEG thumbnail (smaller, under YouTube's 2MB limit)
            thumb_jpg = short_out / "thumbnail.jpg"
            thumb_png = short_out / "thumbnail.png"
            thumb = thumb_jpg if thumb_jpg.exists() else thumb_png

            # Log key: ja keeps bare sid for backward compat with existing logs;
            # non-ja uses `{sid}__{lang}` so each language version tracks separately.
            log_key = sid if args.language == "ja" else f"{sid}__{args.language}"

            if log_key in log["uploads"] and log["uploads"][log_key].get("video_id") and not args.force:
                print(f"\n[{idx}/{len(short_yamls)}] {log_key} — already uploaded as {log['uploads'][log_key]['video_id']}, skipping")
                continue

            if not video_mp4.exists():
                print(f"\n[{idx}/{len(short_yamls)}] {sid} — MISSING {video_mp4}, run short_gen first", file=sys.stderr)
                continue

            parent_video_id = _parent_video_id(conn, args.project_id, cfg.get("parent_chapter", ""))
            if not parent_video_id:
                print(f"  ⚠️ parent chapter '{cfg.get('parent_chapter')}' not found in DB — short will not be linked")

            # Language-aware title/description lookup:
            # 1) cfg[lang][field]            (v2: top-level language section)
            # 2) cfg['i18n'][lang][field]    (v1)
            # 3) cfg[f'{field}_{lang}']      (v1 suffix style)
            # 4) cfg[field]                  (v1 top-level, assumed JA)
            def _lf(field: str):
                v2 = cfg.get(args.language)
                if isinstance(v2, dict) and field in v2:
                    return v2[field]
                i18n = (cfg.get("i18n") or {}).get(args.language, {})
                if field in i18n:
                    return i18n[field]
                key = f"{field}_{args.language}"
                if key in cfg:
                    return cfg[key]
                return cfg.get(field, "")

            title = _lf("title") or cfg.get("title", "")
            description = _lf("description") or cfg.get("description", "")
            tags_str = _lf("tags") or cfg.get("tags", "Shorts,biography,伝記,アニメ")
            if not title:
                print(f"  ⚠️ {sid}: no title found for language={args.language}, skipping", file=sys.stderr)
                continue
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            if "Shorts" not in tags:
                tags.insert(0, "Shorts")

            print(f"\n[{idx}/{len(short_yamls)}] uploading {sid}: {title}")
            print(f"  video : {video_mp4}  ({video_mp4.stat().st_size/1024/1024:.1f} MiB)")
            if thumb.exists():
                print(f"  thumb : {thumb}")
            if parent_video_id:
                print(f"  parent: {parent_video_id}  (ch={cfg.get('parent_chapter')})")

            try:
                resp = upload(
                    video_path=video_mp4,
                    title=title,
                    description=description,
                    privacy=args.privacy,
                    category_id="22",
                    tags=tags,
                    client_secret_path=args.client_secret,
                    token_path=args.token,
                    port=args.port,
                    thumbnail_path=thumb if thumb.exists() else None,
                )
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                log["uploads"][log_key] = {"error": str(e), "ts": datetime.utcnow().isoformat()}
                _save_log(log_path, log)
                continue

            vid = resp.get("id")
            log["uploads"][log_key] = {
                "video_id": vid,
                "title": title,
                "language": args.language,
                "ts": datetime.utcnow().isoformat(),
                "url_studio": f"https://studio.youtube.com/video/{vid}/edit" if vid else None,
                "parent_video_id": parent_video_id,
            }
            _save_log(log_path, log)

            # DB upsert
            upsert_video(
                conn,
                video_id=vid,
                series_id=args.project_id,
                chapter_id=cfg.get("parent_chapter"),
                kind="short",
                parent_video_id=parent_video_id,
                title=title,
                description=description,
                tags=tags,
                privacy=args.privacy,
                master_mp4_path=str(video_mp4),
                thumbnail_path=str(thumb) if thumb.exists() else None,
                channel_id=args.channel,
                metadata={"short_id": sid, "config": cfg},
            )
            conn.commit()
            print(f"  ✓ uploaded — video_id={vid}")
            time.sleep(0.3)

    print(f"\n=== done. log: {log_path} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
