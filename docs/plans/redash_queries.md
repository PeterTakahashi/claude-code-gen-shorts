# Redash queries (webtoon-gen analytics)

Copy-paste these into Redash (Queries → New Query → select `webtoon` data source → paste SQL → Save).

---

## Q1. チャンネル別 累計再生数の推移 (line chart, time series)

```sql
WITH per_video_daily AS (
  SELECT DISTINCT ON (video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'))
    DATE(fetched_at AT TIME ZONE 'Asia/Tokyo') AS date,
    video_id, view_count, like_count, comment_count
  FROM video_stats
  ORDER BY video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'), fetched_at DESC
)
SELECT
  d.date,
  c.display_name AS channel,
  SUM(d.view_count) AS views
FROM per_video_daily d
JOIN videos v USING (video_id)
JOIN channels c ON c.id = v.channel_id
WHERE v.superseded_by IS NULL
  AND (v.metadata->>'deleted_at') IS NULL
GROUP BY d.date, c.display_name
ORDER BY d.date, channel;
```

**Visualization**: Chart → Line → X: `date`, Y: `views`, Group by: `channel`

---

## Q2. チャンネル別 累計いいねの推移

同じ pattern で `views` → `likes`:

```sql
WITH per_video_daily AS (
  SELECT DISTINCT ON (video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'))
    DATE(fetched_at AT TIME ZONE 'Asia/Tokyo') AS date,
    video_id, like_count
  FROM video_stats
  ORDER BY video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'), fetched_at DESC
)
SELECT
  d.date,
  c.display_name AS channel,
  SUM(d.like_count) AS likes
FROM per_video_daily d
JOIN videos v USING (video_id)
JOIN channels c ON c.id = v.channel_id
WHERE v.superseded_by IS NULL
  AND (v.metadata->>'deleted_at') IS NULL
GROUP BY d.date, c.display_name
ORDER BY d.date, channel;
```

---

## Q3. チャンネル別 累計コメント数の推移

```sql
WITH per_video_daily AS (
  SELECT DISTINCT ON (video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'))
    DATE(fetched_at AT TIME ZONE 'Asia/Tokyo') AS date,
    video_id, comment_count
  FROM video_stats
  ORDER BY video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'), fetched_at DESC
)
SELECT
  d.date,
  c.display_name AS channel,
  SUM(d.comment_count) AS comments
FROM per_video_daily d
JOIN videos v USING (video_id)
JOIN channels c ON c.id = v.channel_id
WHERE v.superseded_by IS NULL
  AND (v.metadata->>'deleted_at') IS NULL
GROUP BY d.date, c.display_name
ORDER BY d.date, channel;
```

---

## Q4. 動画別 (1チャンネル絞込) 再生数推移 — パラメータ付き

Redashの **{{channel}}** パラメータ機能 (Dropdown List) で切り替え可。

```sql
SELECT
  v.title || ' (' || v.video_id || ')' AS video,
  s.fetched_at AT TIME ZONE 'Asia/Tokyo' AS at,
  s.view_count AS views,
  s.like_count AS likes
FROM video_stats s
JOIN videos v USING (video_id)
WHERE v.channel_id = '{{channel}}'
  AND v.superseded_by IS NULL
  AND (v.metadata->>'deleted_at') IS NULL
ORDER BY at, video;
```

**Parameter**: Add Parameter → `channel` → Type: Dropdown List → values from
```sql
SELECT id, display_name FROM channels ORDER BY display_name;
```
**Visualization**: Line chart, X: `at`, Y: `views`, Group by: `video`

---

## Q5. チャンネル summary テーブル (今この瞬間)

```sql
WITH latest AS (
  SELECT DISTINCT ON (video_id)
    video_id, view_count, like_count, comment_count
  FROM video_stats
  ORDER BY video_id, fetched_at DESC
)
SELECT
  c.display_name AS channel,
  COUNT(*) AS videos,
  SUM(l.view_count) AS views,
  SUM(l.like_count) AS likes,
  SUM(l.comment_count) AS comments,
  ROUND((SUM(l.like_count)::numeric / NULLIF(SUM(l.view_count), 0)) * 1000, 1)
    AS likes_per_1k_views
FROM latest l
JOIN videos v USING (video_id)
JOIN channels c ON c.id = v.channel_id
WHERE v.superseded_by IS NULL
  AND (v.metadata->>'deleted_at') IS NULL
GROUP BY c.display_name, v.channel_id
ORDER BY views DESC;
```

**Visualization**: Table (default).

---

## Q6. TOP 30 動画 (横断)

```sql
WITH latest AS (
  SELECT DISTINCT ON (video_id)
    video_id, view_count, like_count, comment_count
  FROM video_stats
  ORDER BY video_id, fetched_at DESC
)
SELECT
  c.display_name AS channel,
  l.view_count AS views,
  l.like_count AS likes,
  l.comment_count AS comments,
  v.video_id,
  v.title,
  'https://youtube.com/shorts/' || v.video_id AS url
FROM latest l
JOIN videos v USING (video_id)
JOIN channels c ON c.id = v.channel_id
WHERE v.superseded_by IS NULL
  AND (v.metadata->>'deleted_at') IS NULL
ORDER BY l.view_count DESC NULLS LAST
LIMIT 30;
```

---

## Dashboard 構成 (推奨)

「Webtoon Analytics」という新規 Dashboard 作成 → 各 query の `Add Widget` で配置:

```
┌─────────────────────────────────────┐
│ Q5 channel summary (table, 全幅)    │
├──────────────────┬──────────────────┤
│ Q1 views (line)  │ Q2 likes (line)  │
├──────────────────┴──────────────────┤
│ Q3 comments (line, 全幅)            │
├─────────────────────────────────────┤
│ Q4 per-video views (drilldown, 全幅)│
├─────────────────────────────────────┤
│ Q6 top 30 videos (table, 全幅)      │
└─────────────────────────────────────┘
```

---

## stats 自動更新 (cron)

Redash 自体に Refresh Schedule あり (各 query で「Refresh Schedule」設定可能、デフォルト None)。
DB自体の stats は別途 cron で `src.youtube_stats_sync` 実行:

```bash
# crontab -e (例: 毎日 19:00 と 23:00 に sync)
0 19,23 * * * cd /Users/apple/dev/claude-code/webtoon-gen && PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_stats_sync --skip-dislikes >> /tmp/stats_sync.log 2>&1
```
