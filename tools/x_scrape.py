#!/usr/bin/env python3
"""Scrape recent tweets from given X accounts via the logged-in Playwright
profile (~/news-pw-profile). Free alternative to the paid X API.

Pipeline:
  x_scrape.py --accounts BloombergJapan nikkei --top 10 --scrolls 3
                |
                v  (top tweets with metrics + URLs)
       news_fetch.py URL ...

First run: pass --login to interactively log into X. The session is then
persisted in ~/news-pw-profile for headless re-use.

Usage:
  # one-time: log into X
  ~/yt-pw/bin/python tools/x_scrape.py --login

  # daily: scrape top tweets
  ~/yt-pw/bin/python tools/x_scrape.py --accounts BloombergJapan nikkei \
      --top 10 --hours 24 --out /tmp/x_top.json
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/news-pw-profile")
REAL_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/126.0.0.0 Safari/537.36")


def parse_count(s: str) -> int:
    """Parse X metric strings like '1.2K', '15M', '2,612' to int."""
    if not s:
        return 0
    s = s.strip().replace(",", "").replace(" ", "")
    if not s:
        return 0
    m = re.match(r"^([\d.]+)\s*([KkMmBb万億])?$", s)
    if not m:
        return 0
    n = float(m.group(1))
    suf = (m.group(2) or "").lower()
    mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000,
            "万": 10_000, "億": 100_000_000}.get(suf, 1)
    return int(n * mult)


def parse_tweet_article(article) -> dict:
    """Extract metrics from one article[data-testid='tweet']. Resilient to
    DOM variations: we mostly rely on text content + a few stable testids."""
    out = {"text": "", "like_count": 0, "retweet_count": 0,
           "reply_count": 0, "view_count": 0, "url": "", "tweet_id": "",
           "created_at": ""}
    # tweet text
    try:
        t = article.query_selector('[data-testid="tweetText"]')
        out["text"] = (t.inner_text() or "").strip() if t else ""
    except Exception:
        pass
    # permalink + tweet id (look for /status/<id>)
    try:
        for a in article.query_selector_all('a[href*="/status/"]'):
            href = a.get_attribute("href") or ""
            m = re.search(r"/status/(\d+)", href)
            if m:
                out["tweet_id"] = m.group(1)
                out["url"] = f"https://x.com{href.split('?')[0]}"
                break
    except Exception:
        pass
    # created_at (datetime attribute of the time element inside the permalink)
    try:
        tm = article.query_selector("time[datetime]")
        if tm:
            out["created_at"] = tm.get_attribute("datetime") or ""
    except Exception:
        pass
    # metrics — likes / retweets / replies / views.
    # Each testid has an aria-label that includes the count.
    for key, testid in (("reply_count", "reply"),
                        ("retweet_count", "retweet"),
                        ("like_count", "like")):
        try:
            el = article.query_selector(f'[data-testid="{testid}"]')
            if not el:
                continue
            aria = el.get_attribute("aria-label") or ""
            num_match = re.search(r"([\d,]+)", aria)
            if num_match:
                out[key] = int(num_match.group(1).replace(",", ""))
            else:
                txt = (el.inner_text() or "").strip()
                out[key] = parse_count(txt.splitlines()[-1] if txt else "")
        except Exception:
            pass
    # views — often in an aria-label on a link near the analytics icon.
    try:
        analytics = article.query_selector('a[href*="/analytics"]')
        if analytics:
            aria = analytics.get_attribute("aria-label") or ""
            num_match = re.search(r"([\d,]+)\s*(views|view|ビュー|表示)", aria, re.I)
            if num_match:
                out["view_count"] = int(num_match.group(1).replace(",", ""))
    except Exception:
        pass
    # outbound article URL — first non-x.com link in the tweet body
    try:
        for a in article.query_selector_all('[data-testid="tweetText"] a, a[role="link"]'):
            href = a.get_attribute("href") or ""
            if not href or href.startswith("/"):
                continue
            if "x.com" in href or "twitter.com" in href or "t.co/" in href:
                # t.co links won't be expanded in DOM; we'll resolve later if needed
                if "t.co/" in href and "out_url" not in out:
                    out["out_url_short"] = href
                continue
            out["out_url"] = href
            break
    except Exception:
        pass
    return out


def scrape_account(page, account: str, scrolls: int, settle: float) -> list[dict]:
    url = f"https://x.com/{account}"
    print(f">>> @{account}", file=sys.stderr, flush=True)
    try:
        page.goto(url, wait_until="commit", timeout=45000)
    except Exception as e:
        print(f"  ! goto: {str(e)[:120]}", file=sys.stderr)
        return []
    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=15000)
    except Exception:
        print(f"  ! tweets did not appear (login required?)", file=sys.stderr)
        return []
    seen_ids = set()
    tweets = []
    for i in range(scrolls + 1):
        time.sleep(settle)
        for art in page.query_selector_all('article[data-testid="tweet"]'):
            try:
                t = parse_tweet_article(art)
            except Exception:
                continue
            tid = t.get("tweet_id")
            if not tid or tid in seen_ids:
                continue
            seen_ids.add(tid)
            t["account"] = account
            tweets.append(t)
        # scroll one viewport down to load more
        if i < scrolls:
            try:
                page.evaluate("window.scrollBy(0, window.innerHeight)")
            except Exception:
                pass
    print(f"  -> {len(tweets)} tweets scraped", file=sys.stderr)
    return tweets


def login_flow(ctx):
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://x.com/login", wait_until="commit", timeout=60000)
    print("\n>>> Log into X in the open browser window.", flush=True)
    print(">>> Waiting up to 3 minutes for login to complete…", flush=True)
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(5)
        try:
            page.goto("https://x.com/home", wait_until="commit", timeout=30000)
            time.sleep(3)
            if page.query_selector('a[data-testid="AppTabBar_Home_Link"]') \
                    or page.query_selector('[data-testid="primaryColumn"]'):
                print("✓ logged in — session saved to ~/news-pw-profile", flush=True)
                return True
        except Exception:
            pass
    print("⚠ login not detected within 3 min", flush=True)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true",
                    help="One-time: open browser for you to log into X manually")
    ap.add_argument("--accounts", nargs="*",
                    help="X usernames without @")
    ap.add_argument("--scrolls", type=int, default=3,
                    help="Viewport scrolls per account (default 3 = ~20-40 tweets)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--rank-by", default="like_count",
                    choices=["like_count", "retweet_count", "view_count",
                             "reply_count"])
    ap.add_argument("--require-out-url", action="store_true",
                    help="Only keep tweets that link to an external article")
    ap.add_argument("--settle", type=float, default=2.0,
                    help="Pause between scrolls (default 2s)")
    ap.add_argument("--headed", action="store_true", default=False)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=not (args.login or args.headed),
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=(args.login or args.headed),
            user_agent=REAL_UA, locale="ja-JP",
        )
        if args.login:
            login_flow(ctx)
            ctx.close()
            return 0
        if not args.accounts:
            print("ERROR: --accounts required (or use --login)", file=sys.stderr)
            ctx.close()
            return 1
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        all_tweets = []
        for acct in args.accounts:
            all_tweets.extend(scrape_account(page, acct, args.scrolls, args.settle))
        ctx.close()

    if args.require_out_url:
        all_tweets = [t for t in all_tweets if t.get("out_url")]
    all_tweets.sort(key=lambda x: x.get(args.rank_by, 0), reverse=True)
    top = all_tweets[:args.top]
    print(f"\n  total {len(all_tweets)} tweets, top {len(top)} by {args.rank_by}",
          file=sys.stderr)

    out = json.dumps(top, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"wrote -> {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
