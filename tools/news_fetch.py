#!/usr/bin/env python3
"""Fetch article bodies from logged-in news sites via the persistent
Playwright profile (~/news-pw-profile). The user logs in manually once;
this tool reuses the resulting cookies to bypass paywalls.

Designed to be the "fetch" half of an idea pipeline:
  search step (Gemini CLI / Google / RSS) -> URLs
                                          -> news_fetch.py -> bodies
                                          -> LLM -> shorts ideas

Usage:
  ~/yt-pw/bin/python tools/news_fetch.py URL [URL ...]
  ~/yt-pw/bin/python tools/news_fetch.py --headed URL ...   # show the browser
  ~/yt-pw/bin/python tools/news_fetch.py --out out.json URL ...

Output: JSON array (stdout or --out file) of
  {url, http_status, title, byline, date, body, body_len, paywall_signal}
"""
import argparse
import json
import os
import re
import sys
import time
from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/news-pw-profile")
REAL_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/126.0.0.0 Safari/537.36")

PAYWALL_PHRASES = [
    # English
    "Subscribe to read", "Subscribe Now", "Get Unlimited Access",
    "subscriber-only", "Sign in to read",
    # Japanese
    "この記事は会員限定", "有料会員限定", "会員登録",
    "続きを読むには", "ログインしてください", "サブスクリプション",
]


def extract_article(page) -> dict:
    """Return {title, byline, date, body, paywall_signal} from the current page.

    Uses query_selector throughout (returns None immediately if not found),
    NOT page.locator (which waits up to the default 30s per call → ~90s total).
    """
    title = ""
    try:
        title = page.title() or ""
    except Exception:
        pass
    og = page.query_selector('meta[property="og:title"]')
    if og:
        c = og.get_attribute("content") or ""
        if c:
            title = c

    byline = ""
    for sel in ('meta[name="author"]', '[itemprop="author"]', '[class*="byline" i]'):
        el = page.query_selector(sel)
        if not el:
            continue
        try:
            byline = (el.get_attribute("content") or el.inner_text() or "").strip()
        except Exception:
            byline = ""
        if byline:
            break

    date = ""
    for sel in ('meta[property="article:published_time"]',
                'meta[name="pubdate"]', 'time[datetime]', '[itemprop="datePublished"]'):
        el = page.query_selector(sel)
        if not el:
            continue
        try:
            date = (el.get_attribute("content") or el.get_attribute("datetime")
                    or el.inner_text() or "").strip()
        except Exception:
            date = ""
        if date:
            break

    body = ""
    for sel in ('article [itemprop="articleBody"]', 'article',
                '[data-component="ArticleBody"]', '[data-component="body"]',
                'main', '.article-body', '.article-content'):
        el = page.query_selector(sel)
        if not el:
            continue
        try:
            text = el.inner_text()
        except Exception:
            continue
        if text and len(text) > 200:
            body = text
            break
    if not body:
        try:
            body = page.query_selector("body").inner_text() or ""
        except Exception:
            body = ""
    # collapse runs of blank lines
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    body_lc = body.lower()
    paywall = [p for p in PAYWALL_PHRASES if p.lower() in body_lc]
    return {
        "title": title.strip(),
        "byline": byline.strip() if byline else "",
        "date": date.strip() if date else "",
        "body": body,
        "body_len": len(body),
        "paywall_signal": paywall,
    }


def fetch_one(page, url: str, settle_seconds: float) -> dict:
    t0 = time.time()
    print(f"  -> {url}", file=sys.stderr, flush=True)
    out = {"url": url, "http_status": None}
    try:
        # 'commit' returns as soon as the navigation is committed (response
        # headers received). News sites' DOMContentLoaded is delayed by tons
        # of synchronous third-party scripts. We then wait briefly for the
        # article element specifically, which is usually present early.
        resp = page.goto(url, wait_until="commit", timeout=30000)
        out["http_status"] = resp.status if resp else None
    except Exception as e:
        out["error"] = f"goto: {str(e)[:200]}"
        return out
    # Wait for any common article container to appear; gives us article body
    # without waiting for analytics/ads. 8s cap.
    try:
        page.wait_for_selector(
            'article, [itemprop="articleBody"], [data-component="ArticleBody"], main',
            state="attached", timeout=8000)
    except Exception:
        pass
    time.sleep(settle_seconds)
    out.update(extract_article(page))
    out["fetch_secs"] = round(time.time() - t0, 1)
    print(f"     {out['fetch_secs']}s  body={out.get('body_len')}", file=sys.stderr, flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--headed", action="store_true",
                    help="Show the browser (default: headless, faster)")
    ap.add_argument("--out", type=str, default=None,
                    help="Write JSON array here (default: stdout)")
    ap.add_argument("--settle", type=float, default=1.5,
                    help="Seconds to wait after DOMContentLoaded (default 1.5)")
    ap.add_argument("--block-ads", action="store_true",
                    help="Block ad/tracker domains (may be slower in practice)")
    args = ap.parse_args()

    # Block heavy ad/tracker domains to mimic "open in a real browser fast".
    BLOCK_PATTERNS = [
        "*googletagmanager.com*", "*google-analytics.com*", "*googlesyndication.com*",
        "*doubleclick.net*", "*adservice.google.com*", "*googleadservices.com*",
        "*facebook.net*", "*facebook.com/tr*", "*scorecardresearch.com*",
        "*chartbeat.com*", "*krxd.net*", "*amazon-adsystem.com*", "*adnxs.com*",
        "*criteo.com*", "*nr-data.net*", "*newrelic.com*", "*hotjar.com*",
        "*omtrdc.net*", "*demdex.net*", "*adsrvr.org*", "*taboola.com*",
        "*outbrain.com*", "*moatads.com*", "*rubiconproject.com*",
        # Media we don't need for text extraction
        "*.mp4", "*.webm", "*.ogg",
    ]

    results = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=not args.headed,
            args=["--disable-blink-features=AutomationControlled"],
            no_viewport=args.headed, user_agent=REAL_UA, locale="ja-JP",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if args.block_ads:
            def block(route):
                u = route.request.url
                if any(p.replace("*", "") in u for p in BLOCK_PATTERNS):
                    return route.abort()
                return route.continue_()
            ctx.route("**/*", block)
        for u in args.urls:
            results.append(fetch_one(page, u, args.settle))
        ctx.close()

    text = json.dumps(results, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {len(results)} articles -> {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
