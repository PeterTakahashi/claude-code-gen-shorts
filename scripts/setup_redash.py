"""Bootstrap Redash data source + queries + dashboard via API.

Requires:
  - Redash running at http://localhost:5001 with admin user already created
  - REDASH_EMAIL + REDASH_PASSWORD in .env (or env vars)

Idempotent: re-running won't duplicate the data source / queries / dashboard
(it finds existing by name and updates / skips).
"""
from __future__ import annotations

import os
import sys
import time
from textwrap import dedent

import httpx
from dotenv import load_dotenv

load_dotenv()

REDASH = os.environ.get("REDASH_URL", "http://localhost:5001")
EMAIL = os.environ.get("REDASH_EMAIL", "")
# Prefer API key from env, else fetch from internal Redash postgres via docker.
API_KEY = os.environ.get("REDASH_API_KEY")
if not API_KEY:
    import subprocess
    try:
        API_KEY = subprocess.check_output(
            ["docker", "exec", "webtoon_redash_postgres",
             "psql", "-U", "redash", "-d", "postgres", "-tA", "-c",
             "SELECT api_key FROM users WHERE id=1;"],
            text=True,
        ).strip()
    except Exception as e:
        print(f"WARN: cannot fetch api_key from redash_postgres ({e})", file=sys.stderr)
        API_KEY = None
if not API_KEY:
    print("ERROR: no REDASH_API_KEY in env and could not fetch from DB", file=sys.stderr)
    raise SystemExit(2)

DS_NAME = "webtoon"
DASH_NAME = "Webtoon Analytics"

QUERIES = [
    {
        "name": "Q1. チャンネル別 累計再生数の推移",
        "sql": dedent("""
            WITH per_video_daily AS (
              SELECT DISTINCT ON (video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'))
                DATE(fetched_at AT TIME ZONE 'Asia/Tokyo') AS date,
                video_id, view_count, like_count, comment_count
              FROM video_stats
              ORDER BY video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'), fetched_at DESC
            )
            SELECT d.date, c.display_name AS channel, SUM(d.view_count) AS views
            FROM per_video_daily d
            JOIN videos v USING (video_id)
            JOIN channels c ON c.id = v.channel_id
            WHERE v.superseded_by IS NULL AND (v.metadata->>'deleted_at') IS NULL
            GROUP BY d.date, c.display_name
            ORDER BY d.date, channel;
        """).strip(),
        "viz": {
            "type": "CHART",
            "name": "channel views over time",
            "options": {
                "globalSeriesType": "line",
                "columnMapping": {"date": "x", "views": "y", "channel": "series"},
                "showDataLabels": False,
                "legend": {"enabled": True, "placement": "auto"},
                "xAxis": {"type": "datetime", "labels": {"enabled": True}, "title": {"text": "date"}},
                "yAxis": [{"type": "linear", "title": {"text": "views"}}, {"type": "linear", "opposite": True}],
            },
        },
    },
    {
        "name": "Q2. チャンネル別 累計いいねの推移",
        "sql": dedent("""
            WITH per_video_daily AS (
              SELECT DISTINCT ON (video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'))
                DATE(fetched_at AT TIME ZONE 'Asia/Tokyo') AS date, video_id, like_count
              FROM video_stats
              ORDER BY video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'), fetched_at DESC
            )
            SELECT d.date, c.display_name AS channel, SUM(d.like_count) AS likes
            FROM per_video_daily d
            JOIN videos v USING (video_id)
            JOIN channels c ON c.id = v.channel_id
            WHERE v.superseded_by IS NULL AND (v.metadata->>'deleted_at') IS NULL
            GROUP BY d.date, c.display_name
            ORDER BY d.date, channel;
        """).strip(),
        "viz": {
            "type": "CHART",
            "name": "channel likes over time",
            "options": {
                "globalSeriesType": "line",
                "columnMapping": {"date": "x", "likes": "y", "channel": "series"},
                "legend": {"enabled": True, "placement": "auto"},
                "xAxis": {"type": "datetime", "labels": {"enabled": True}, "title": {"text": "date"}},
                "yAxis": [{"type": "linear", "title": {"text": "likes"}}, {"type": "linear", "opposite": True}],
            },
        },
    },
    {
        "name": "Q3. チャンネル別 累計コメント数の推移",
        "sql": dedent("""
            WITH per_video_daily AS (
              SELECT DISTINCT ON (video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'))
                DATE(fetched_at AT TIME ZONE 'Asia/Tokyo') AS date, video_id, comment_count
              FROM video_stats
              ORDER BY video_id, DATE(fetched_at AT TIME ZONE 'Asia/Tokyo'), fetched_at DESC
            )
            SELECT d.date, c.display_name AS channel, SUM(d.comment_count) AS comments
            FROM per_video_daily d
            JOIN videos v USING (video_id)
            JOIN channels c ON c.id = v.channel_id
            WHERE v.superseded_by IS NULL AND (v.metadata->>'deleted_at') IS NULL
            GROUP BY d.date, c.display_name
            ORDER BY d.date, channel;
        """).strip(),
        "viz": {
            "type": "CHART",
            "name": "channel comments over time",
            "options": {
                "globalSeriesType": "line",
                "columnMapping": {"date": "x", "comments": "y", "channel": "series"},
                "legend": {"enabled": True, "placement": "auto"},
                "xAxis": {"type": "datetime", "labels": {"enabled": True}, "title": {"text": "date"}},
                "yAxis": [{"type": "linear", "title": {"text": "comments"}}, {"type": "linear", "opposite": True}],
            },
        },
    },
    {
        "name": "Q4. チャンネル summary",
        "sql": dedent("""
            WITH latest AS (
              SELECT DISTINCT ON (video_id) video_id, view_count, like_count, comment_count
              FROM video_stats ORDER BY video_id, fetched_at DESC
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
            WHERE v.superseded_by IS NULL AND (v.metadata->>'deleted_at') IS NULL
            GROUP BY c.display_name, v.channel_id
            ORDER BY views DESC NULLS LAST;
        """).strip(),
        "viz": None,  # default Table viz is auto-created
    },
    {
        "name": "Q5. TOP 30 動画",
        "sql": dedent("""
            WITH latest AS (
              SELECT DISTINCT ON (video_id) video_id, view_count, like_count, comment_count
              FROM video_stats ORDER BY video_id, fetched_at DESC
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
            WHERE v.superseded_by IS NULL AND (v.metadata->>'deleted_at') IS NULL
            ORDER BY l.view_count DESC NULLS LAST
            LIMIT 30;
        """).strip(),
        "viz": None,
    },
    {
        # Counter widgets (Total Views/Likes/Comments) live on this query.
        # Listed here so re-running the script refreshes them too.
        "name": "Q6. 全チャンネル合計 (views/likes/comments)",
        "sql": dedent("""
            WITH latest AS (
              SELECT DISTINCT ON (video_id) video_id, view_count, like_count, comment_count
              FROM video_stats ORDER BY video_id, fetched_at DESC
            )
            SELECT
              COALESCE(SUM(l.view_count), 0)    AS total_views,
              COALESCE(SUM(l.like_count), 0)    AS total_likes,
              COALESCE(SUM(l.comment_count), 0) AS total_comments
            FROM latest l
            JOIN videos v USING (video_id)
            WHERE v.superseded_by IS NULL
              AND (v.metadata->>'deleted_at') IS NULL;
        """).strip(),
        "viz": None,  # counter visualizations already exist; just refresh the query
    },
]


def make_client() -> httpx.Client:
    """Return an httpx client preconfigured with Redash API key auth."""
    return httpx.Client(
        base_url=REDASH,
        timeout=30.0,
        headers={"Authorization": f"Key {API_KEY}"},
    )


def find_or_create_datasource(c: httpx.Client) -> int:
    r = c.get("/api/data_sources")
    r.raise_for_status()
    for ds in r.json():
        if ds["name"] == DS_NAME:
            print(f"  data source '{DS_NAME}' already exists (id={ds['id']})")
            return ds["id"]
    body = {
        "name": DS_NAME,
        "type": "pg",
        "options": {
            "host": "postgres",
            "port": 5432,
            "user": "webtoon",
            "password": "webtoon",
            "dbname": "webtoon",
        },
    }
    r = c.post("/api/data_sources", json=body)
    r.raise_for_status()
    ds_id = r.json()["id"]
    print(f"  created data source '{DS_NAME}' (id={ds_id})")
    return ds_id


def find_or_create_query(c: httpx.Client, ds_id: int, q: dict) -> dict:
    """Return the query dict (with .id and .latest_query_data_id)."""
    r = c.get("/api/queries", params={"q": q["name"]})
    r.raise_for_status()
    for existing in r.json().get("results", []):
        if existing["name"] == q["name"]:
            # update query text if changed
            patch = {"name": q["name"], "query": q["sql"], "data_source_id": ds_id}
            r = c.post(f"/api/queries/{existing['id']}", json=patch)
            r.raise_for_status()
            print(f"  updated query '{q['name']}' (id={existing['id']})")
            return r.json()
    body = {"name": q["name"], "query": q["sql"], "data_source_id": ds_id, "schedule": None, "options": {}}
    r = c.post("/api/queries", json=body)
    r.raise_for_status()
    created = r.json()
    print(f"  created query '{q['name']}' (id={created['id']})")
    # Publish (otherwise dashboard widgets show errors)
    c.post(f"/api/queries/{created['id']}", json={"is_draft": False})
    return created


def run_query(c: httpx.Client, query_id: int) -> int | None:
    """Execute a query and wait for result. Returns query_result_id or None on timeout."""
    r = c.post(f"/api/queries/{query_id}/results", json={"parameters": {}, "max_age": 0})
    if r.status_code != 200:
        print(f"  ⚠️ exec query {query_id}: {r.status_code} {r.text[:200]}")
        return None
    body = r.json()
    if "query_result" in body:
        return body["query_result"]["id"]
    job_id = body["job"]["id"]
    for _ in range(30):
        time.sleep(2)
        r2 = c.get(f"/api/jobs/{job_id}")
        if r2.status_code != 200:
            continue
        j = r2.json().get("job", {})
        if j.get("status") in (3,):  # success
            return j.get("query_result_id")
        if j.get("status") in (4,):  # failure
            print(f"  ⚠️ query {query_id} failed: {j.get('error')}")
            return None
    print(f"  ⚠️ query {query_id} timed out")
    return None


def ensure_visualization(c: httpx.Client, query_id: int, viz_spec: dict | None) -> int:
    """Create a chart visualization if specified. Returns viz_id (or table viz if None)."""
    r = c.get(f"/api/queries/{query_id}")
    r.raise_for_status()
    existing = r.json().get("visualizations", [])
    target_name = (viz_spec or {}).get("name") or "Table"
    for v in existing:
        if v["name"] == target_name:
            return v["id"]
    if viz_spec is None:
        # Table viz is auto-created with the query
        for v in existing:
            if v["type"] == "TABLE":
                return v["id"]
        return existing[0]["id"]
    body = {
        "name": viz_spec["name"],
        "type": viz_spec["type"],
        "options": viz_spec["options"],
        "query_id": query_id,
    }
    r = c.post("/api/visualizations", json=body)
    r.raise_for_status()
    return r.json()["id"]


def find_or_create_dashboard(c: httpx.Client, name: str) -> dict:
    r = c.get("/api/dashboards", params={"q": name})
    r.raise_for_status()
    for d in r.json().get("results", []):
        if d["name"] == name:
            print(f"  dashboard '{name}' already exists (id={d['id']}, slug={d['slug']})")
            return d
    r = c.post("/api/dashboards", json={"name": name})
    r.raise_for_status()
    created = r.json()
    print(f"  created dashboard '{name}' (id={created['id']}, slug={created['slug']})")
    return created


def add_widget(c: httpx.Client, dash_id: int, viz_id: int, row: int, col: int, width: int, height: int = 8) -> None:
    body = {
        "dashboard_id": dash_id,
        "visualization_id": viz_id,
        "width": width,
        "options": {
            "isHidden": False,
            "position": {"autoHeight": False, "sizeX": width, "sizeY": height, "minSizeX": 1, "maxSizeX": 6,
                          "minSizeY": 1, "maxSizeY": 1000, "col": col, "row": row},
        },
        "text": "",
    }
    r = c.post("/api/widgets", json=body)
    if r.status_code != 200:
        print(f"  ⚠️ add widget failed: {r.status_code} {r.text[:200]}")


def publish_dashboard(c: httpx.Client, dash_id: int) -> None:
    c.post(f"/api/dashboards/{dash_id}", json={"is_draft": False})


def main() -> int:
    print(f"=== Redash setup at {REDASH} ===")
    c = make_client()
    # sanity check the api key (avoid /api/users/me — broken in Redash 25)
    r = c.get("/api/data_sources")
    if r.status_code != 200:
        print(f"ERROR: api key auth failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return 1
    print(f"  api key OK (existing data sources: {len(r.json())})")

    ds_id = find_or_create_datasource(c)

    # 1. Create queries + visualizations
    viz_ids: list[int] = []
    for q in QUERIES:
        created = find_or_create_query(c, ds_id, q)
        qid = created["id"]
        # Run query so the viz has data (best-effort)
        run_query(c, qid)
        vid = ensure_visualization(c, qid, q["viz"])
        viz_ids.append(vid)
        print(f"    → query_id={qid}  viz_id={vid}")

    # 2. Dashboard
    dash = find_or_create_dashboard(c, DASH_NAME)
    # only add widgets if dashboard is empty
    r = c.get(f"/api/dashboards/{dash['slug']}")
    if r.status_code == 200:
        existing_widgets = r.json().get("widgets", [])
        if existing_widgets:
            print(f"  dashboard has {len(existing_widgets)} widgets already, skipping layout")
        else:
            # Layout: 12-col grid, 6 per row in redash
            # Q1 left (0..2), Q2 right (3..5) row 0
            # Q3 full row 8
            # Q4 summary full row 16
            # Q5 top30 full row 24
            add_widget(c, dash["id"], viz_ids[0], row=0, col=0, width=3, height=8)
            add_widget(c, dash["id"], viz_ids[1], row=0, col=3, width=3, height=8)
            add_widget(c, dash["id"], viz_ids[2], row=8, col=0, width=6, height=8)
            add_widget(c, dash["id"], viz_ids[3], row=16, col=0, width=6, height=8)
            add_widget(c, dash["id"], viz_ids[4], row=24, col=0, width=6, height=10)
            print(f"  added 5 widgets")

    publish_dashboard(c, dash["id"])
    print(f"\n✅ open: {REDASH}/dashboards/{dash['slug']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
