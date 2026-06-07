"""Postgres connection + helpers for webtoon-gen.

Reads DB connection from environment (`.env`):
  POSTGRES_HOST     (default 127.0.0.1)
  POSTGRES_PORT     (default 5433 — matches docker-compose.yml)
  POSTGRES_USER     (default webtoon)
  POSTGRES_PASSWORD (default webtoon)
  POSTGRES_DB       (default webtoon)

Usage:
  from src.db import connect, upsert_video, insert_stats
  with connect() as conn:
      upsert_video(conn, video_id=..., series_id=..., title=...)

Run the schema with `docker compose up -d` once — Postgres auto-applies
`db/init/*.sql` on first start. To re-apply after editing schema:
  docker compose exec postgres psql -U webtoon -d webtoon -f /docker-entrypoint-initdb.d/001_schema.sql
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', '127.0.0.1')} "
        f"port={os.getenv('POSTGRES_PORT', '5433')} "
        f"user={os.getenv('POSTGRES_USER', 'webtoon')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'webtoon')} "
        f"dbname={os.getenv('POSTGRES_DB', 'webtoon')}"
    )


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(_dsn()) as conn:
        yield conn


def upsert_channel(
    conn: psycopg.Connection,
    *,
    channel_id: str,
    youtube_channel_id: str | None = None,
    display_name: str,
    theme: str,
    language: str,
    oauth_token_file: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO channels (id, youtube_channel_id, display_name, theme, language, oauth_token_file, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            youtube_channel_id = COALESCE(EXCLUDED.youtube_channel_id, channels.youtube_channel_id),
            display_name = EXCLUDED.display_name,
            theme = EXCLUDED.theme,
            language = EXCLUDED.language,
            oauth_token_file = COALESCE(EXCLUDED.oauth_token_file, channels.oauth_token_file),
            metadata = COALESCE(channels.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
        """,
        (channel_id, youtube_channel_id, display_name, theme, language, oauth_token_file,
         json.dumps(metadata) if metadata else None),
    )


def get_channel_token(conn: psycopg.Connection, channel_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT oauth_token_file FROM channels WHERE id = %s", (channel_id,))
        row = cur.fetchone()
        return row[0] if row else None


def list_channels(conn: psycopg.Connection, *, theme: str | None = None, language: str | None = None) -> list[dict]:
    sql = "SELECT id, display_name, theme, language, oauth_token_file FROM channels"
    where, params = [], []
    if theme:
        where.append("theme = %s"); params.append(theme)
    if language:
        where.append("language = %s"); params.append(language)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def upsert_series(
    conn: psycopg.Connection,
    *,
    series_id: str,
    title_ja: str,
    subject: str | None = None,
    series_short: str | None = None,
    theme: str | None = None,
    language: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO series (id, title_ja, subject, series_short, theme, language, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title_ja = EXCLUDED.title_ja,
            subject = COALESCE(EXCLUDED.subject, series.subject),
            series_short = COALESCE(EXCLUDED.series_short, series.series_short),
            theme = COALESCE(EXCLUDED.theme, series.theme),
            language = COALESCE(EXCLUDED.language, series.language),
            metadata = COALESCE(series.metadata, '{}'::jsonb)
                       || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
        """,
        (series_id, title_ja, subject, series_short, theme, language,
         json.dumps(metadata) if metadata else None),
    )


def upsert_video(
    conn: psycopg.Connection,
    *,
    video_id: str,
    series_id: str | None = None,
    chapter_id: str | None = None,
    kind: str = "long",
    parent_video_id: str | None = None,
    title: str,
    description: str | None = None,
    tags: list[str] | None = None,
    privacy: str = "private",
    category_id: str = "22",
    duration_seconds: float | None = None,
    file_size_bytes: int | None = None,
    master_mp4_path: str | None = None,
    thumbnail_path: str | None = None,
    channel_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Insert a video row, or update it if the same video_id already exists."""
    conn.execute(
        """
        INSERT INTO videos (
            video_id, series_id, chapter_id, kind, parent_video_id,
            title, description, tags, privacy, category_id,
            duration_seconds, file_size_bytes,
            master_mp4_path, thumbnail_path, channel_id, metadata
        ) VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s, %s,%s,%s,%s)
        ON CONFLICT (video_id) DO UPDATE SET
            series_id        = EXCLUDED.series_id,
            chapter_id       = EXCLUDED.chapter_id,
            kind             = EXCLUDED.kind,
            parent_video_id  = EXCLUDED.parent_video_id,
            title            = EXCLUDED.title,
            description      = EXCLUDED.description,
            tags             = EXCLUDED.tags,
            privacy          = EXCLUDED.privacy,
            category_id      = EXCLUDED.category_id,
            duration_seconds = EXCLUDED.duration_seconds,
            file_size_bytes  = EXCLUDED.file_size_bytes,
            master_mp4_path  = EXCLUDED.master_mp4_path,
            thumbnail_path   = EXCLUDED.thumbnail_path,
            channel_id       = COALESCE(EXCLUDED.channel_id, videos.channel_id),
            metadata         = COALESCE(EXCLUDED.metadata, videos.metadata)
        """,
        (
            video_id, series_id, chapter_id, kind, parent_video_id,
            title, description, tags, privacy, category_id,
            duration_seconds, file_size_bytes,
            master_mp4_path, thumbnail_path, channel_id,
            json.dumps(metadata) if metadata else None,
        ),
    )


def mark_superseded(conn: psycopg.Connection, *, old_video_id: str, new_video_id: str) -> None:
    """Mark a duplicate (older) upload as superseded by a newer one."""
    conn.execute(
        "UPDATE videos SET superseded_by = %s WHERE video_id = %s",
        (new_video_id, old_video_id),
    )


def insert_stats(
    conn: psycopg.Connection,
    *,
    video_id: str,
    view_count: int | None,
    like_count: int | None,
    comment_count: int | None,
    dislike_count: int | None = None,
    favorite_count: int | None = None,
    raw: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO video_stats
            (video_id, view_count, like_count, dislike_count, comment_count, favorite_count, raw)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            video_id, view_count, like_count, dislike_count, comment_count, favorite_count,
            json.dumps(raw) if raw else None,
        ),
    )


def list_active_videos(conn: psycopg.Connection, series_id: str | None = None) -> list[dict]:
    """Return videos that have not been superseded. Useful for stats sync."""
    sql = "SELECT video_id, series_id, chapter_id, kind, title FROM videos WHERE superseded_by IS NULL"
    params: tuple = ()
    if series_id:
        sql += " AND series_id = %s"
        params = (series_id,)
    sql += " ORDER BY series_id, kind, chapter_id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
