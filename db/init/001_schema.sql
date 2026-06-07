-- webtoon-gen schema. Auto-applied by postgres image on first start
-- (docker-entrypoint-initdb.d). Idempotent so it can be re-run safely.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- YouTube channels we operate. Each has a theme + language.
-- 1 person × 2 languages = uploaded as 2 separate videos to 2 channels
-- (e.g. 偉人伝 = ja-biography, Baltoon Biography = en-biography).
CREATE TABLE IF NOT EXISTS channels (
    id                  TEXT PRIMARY KEY,           -- internal: 'ijinden_ja', 'baltoon_biography_en'
    youtube_channel_id  TEXT UNIQUE,                -- UCSJvtb0ZJg6P6X8QIweBsRA
    display_name        TEXT NOT NULL,
    theme               TEXT NOT NULL CHECK (theme IN ('biography', 'corporate_incidents', 'corporate_history', 'national_history', 'startup_news', 'science', 'love_psych', 'math', 'war_history', 'mystery', 'astronomy', 'animals', 'corporate_fall', 'crypto_incidents', 'japan_praise', 'artisan', 'serendipity', 'mens_love', 'sports_legends', 'housing_regret', 'money_failure')),
    language            TEXT NOT NULL CHECK (language IN ('ja', 'en', 'zh', 'ko')),
    oauth_token_file    TEXT,                       -- path relative to repo root (e.g. '.youtube_token.ijinden.json')
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata            JSONB
);

-- Top-level grouping (e.g. one row per biography series).
CREATE TABLE IF NOT EXISTS series (
    id            TEXT PRIMARY KEY,                -- 'stevejobs', 'elonmusk'
    title_ja      TEXT NOT NULL,                   -- 'スティーブ・ジョブズ伝'
    subject       TEXT,                            -- 'スティーブ・ジョブズ'
    series_short  TEXT,                            -- 'ジョブズ伝'
    theme         TEXT CHECK (theme IN ('biography', 'corporate_incidents', 'corporate_history', 'national_history', 'startup_news', 'science', 'love_psych', 'math', 'war_history', 'mystery', 'astronomy', 'animals', 'corporate_fall', 'crypto_incidents', 'japan_praise', 'artisan', 'serendipity', 'mens_love', 'sports_legends', 'housing_regret', 'money_failure')),
    language      TEXT CHECK (language IN ('ja', 'en', 'zh', 'ko')) DEFAULT 'ja',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata      JSONB
);

-- One row per video uploaded (or planned to upload) to YouTube.
-- Includes both long-form chapter videos and shorts.
CREATE TABLE IF NOT EXISTS videos (
    video_id          TEXT PRIMARY KEY,            -- YouTube videoId (canonical key)
    series_id         TEXT REFERENCES series(id) ON DELETE SET NULL,
    chapter_id        TEXT,                        -- 'ch1', 'main', 'ch12'
    kind              TEXT NOT NULL DEFAULT 'long' -- 'long' (main chapter) or 'short' (shorts funnel)
                          CHECK (kind IN ('long', 'short')),
    parent_video_id   TEXT REFERENCES videos(video_id) ON DELETE SET NULL,
                                                   -- shorts point back to the long-form they funnel to
    title             TEXT NOT NULL,
    description       TEXT,
    tags              TEXT[],                      -- comma-list parsed into array
    privacy           TEXT NOT NULL DEFAULT 'private'
                          CHECK (privacy IN ('private', 'unlisted', 'public')),
    category_id       TEXT DEFAULT '22',           -- YouTube categoryId
    duration_seconds  REAL,
    file_size_bytes   BIGINT,
    master_mp4_path   TEXT,                        -- local path of mp4
    thumbnail_path    TEXT,                        -- local path of png
    channel_id        TEXT REFERENCES channels(id),-- which YouTube channel this video was uploaded to
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by     TEXT REFERENCES videos(video_id) ON DELETE SET NULL,
                                                   -- mark old duplicates that should be deleted
    metadata          JSONB
);

CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);

CREATE INDEX IF NOT EXISTS idx_videos_series ON videos(series_id);
CREATE INDEX IF NOT EXISTS idx_videos_chapter ON videos(series_id, chapter_id);
CREATE INDEX IF NOT EXISTS idx_videos_kind ON videos(kind);
CREATE INDEX IF NOT EXISTS idx_videos_parent ON videos(parent_video_id);
CREATE INDEX IF NOT EXISTS idx_videos_active ON videos(series_id, chapter_id) WHERE superseded_by IS NULL;

-- Append-only stats snapshots from YouTube Data API v3.
-- A row per (video_id, fetched_at) — fetch periodically (cron / scheduled task).
CREATE TABLE IF NOT EXISTS video_stats (
    id              BIGSERIAL PRIMARY KEY,
    video_id        TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    view_count      BIGINT,
    like_count      BIGINT,
    dislike_count   BIGINT,             -- only available via YouTube Analytics API (channel owner)
    comment_count   BIGINT,
    favorite_count  BIGINT,
    raw             JSONB
);

CREATE INDEX IF NOT EXISTS idx_stats_video_time
    ON video_stats(video_id, fetched_at DESC);

-- Convenience view: latest stats per video joined with video metadata.
CREATE OR REPLACE VIEW v_videos_latest AS
SELECT
    v.video_id,
    v.series_id,
    v.chapter_id,
    v.kind,
    v.parent_video_id,
    v.title,
    v.privacy,
    v.duration_seconds,
    v.uploaded_at,
    v.superseded_by,
    s.view_count,
    s.like_count,
    s.comment_count,
    s.fetched_at AS stats_fetched_at
FROM videos v
LEFT JOIN LATERAL (
    SELECT view_count, like_count, comment_count, fetched_at
    FROM video_stats
    WHERE video_id = v.video_id
    ORDER BY fetched_at DESC
    LIMIT 1
) s ON true;
