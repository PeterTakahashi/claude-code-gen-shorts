#!/usr/bin/env python3
"""Fetch recent tweets from given X accounts, rank by engagement, and emit the
linked-article URLs. Designed as the "search" half of the idea pipeline:

  x_trending.py --accounts BloombergJapan nikkei --hours 24 --top 10
                      |
                      v  (top tweets with URLs)
              news_fetch.py URL ...    (paid-subscription fetch)
                      |
                      v
              LLM ideation -> shorts

Reads X_Bearer_Token from .env. Uses Twitter API v2:
  GET /2/users/by/username/:username
  GET /2/users/:id/tweets ?tweet.fields=public_metrics,entities,created_at

Output (stdout or --out): JSON array of
  {account, tweet_id, created_at, text, like_count, retweet_count,
   reply_count, impression_count, url}
sorted by like_count desc (or --rank-by).

Usage:
  .venv/bin/python tools/x_trending.py --accounts BloombergJapan nikkei \\
                                       --hours 24 --top 10
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import dotenv_values

ROOT = "/Users/apple/dev/claude-code/webtoon-gen"
env = dotenv_values(f"{ROOT}/.env")
BEARER = env.get("X_Bearer_Token") or env.get("X_BEARER_TOKEN")
if not BEARER:
    print("ERROR: X_Bearer_Token missing in .env", file=sys.stderr)
    sys.exit(1)
H = {"Authorization": f"Bearer {BEARER}", "User-Agent": "webtoon-gen/x_trending"}


def get_user_id(username: str) -> str | None:
    r = requests.get(f"https://api.twitter.com/2/users/by/username/{username}",
                     headers=H, timeout=15)
    if r.status_code != 200:
        print(f"  ! {username}: {r.status_code} {r.text[:160]}", file=sys.stderr)
        return None
    return r.json().get("data", {}).get("id")


def get_tweets(user_id: str, since_iso: str, max_results: int = 100) -> list[dict]:
    """Recent tweets (excluding retweets/replies) with engagement metrics."""
    params = {
        "tweet.fields": "public_metrics,entities,created_at",
        "max_results": min(max(max_results, 5), 100),
        "start_time": since_iso,
        "exclude": "retweets,replies",
    }
    r = requests.get(f"https://api.twitter.com/2/users/{user_id}/tweets",
                     headers=H, params=params, timeout=20)
    if r.status_code != 200:
        print(f"  ! tweets fetch: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return []
    return r.json().get("data", []) or []


def extract_url(t: dict, allow_domains: list[str]) -> str | None:
    """Return the first non-x.com URL from entities.urls (prefer expanded_url)."""
    urls = (t.get("entities") or {}).get("urls") or []
    for u in urls:
        expanded = u.get("expanded_url") or u.get("unwound_url") or u.get("url")
        if not expanded:
            continue
        if "x.com" in expanded or "twitter.com" in expanded:
            continue
        if allow_domains and not any(d in expanded for d in allow_domains):
            continue
        return expanded
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", nargs="+", required=True,
                    help="X usernames (without @), e.g. BloombergJapan nikkei")
    ap.add_argument("--hours", type=int, default=24,
                    help="Look-back window in hours (default 24)")
    ap.add_argument("--top", type=int, default=10,
                    help="Top N tweets to return (default 10)")
    ap.add_argument("--rank-by", default="like_count",
                    choices=["like_count", "retweet_count", "impression_count",
                             "reply_count", "engagement"],
                    help="public_metrics field to sort by")
    ap.add_argument("--require-url", action="store_true",
                    help="Only keep tweets that linked to an article")
    ap.add_argument("--allow-domains", nargs="*", default=[],
                    help="Filter URLs to these domain substrings (e.g. bloomberg nikkei)")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    # Twitter API requires strict RFC3339 without microseconds (e.g. "2026-05-27T15:37:14Z").
    since = ((datetime.now(timezone.utc) - timedelta(hours=args.hours))
             .replace(microsecond=0)
             .isoformat()
             .replace("+00:00", "Z"))
    all_tweets = []
    for acct in args.accounts:
        print(f">>> @{acct}", file=sys.stderr, flush=True)
        uid = get_user_id(acct)
        if not uid:
            continue
        for t in get_tweets(uid, since):
            m = t.get("public_metrics") or {}
            engagement = (m.get("like_count", 0) + m.get("retweet_count", 0)
                          + m.get("reply_count", 0))
            url = extract_url(t, args.allow_domains)
            if args.require_url and not url:
                continue
            all_tweets.append({
                "account": acct,
                "tweet_id": t.get("id"),
                "created_at": t.get("created_at"),
                "text": (t.get("text") or "").strip(),
                "like_count": m.get("like_count", 0),
                "retweet_count": m.get("retweet_count", 0),
                "reply_count": m.get("reply_count", 0),
                "impression_count": m.get("impression_count", 0),
                "engagement": engagement,
                "url": url,
            })

    key = args.rank_by
    all_tweets.sort(key=lambda x: x.get(key, 0), reverse=True)
    top = all_tweets[:args.top]
    print(f"  -> {len(all_tweets)} tweets fetched, top {len(top)} by {key}",
          file=sys.stderr, flush=True)

    out = json.dumps(top, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"wrote {len(top)} -> {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
