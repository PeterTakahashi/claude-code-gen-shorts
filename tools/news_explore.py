#!/usr/bin/env python3
"""Lightly explore Nikkei + Bloomberg as a logged-in user.

Uses the persistent ~/news-pw-profile (already authenticated). For each site:
  1. Open homepage, confirm logged-in indicator
  2. Open a relevant category (markets / tech / politics / world)
  3. Open the first article link from that category, screenshot, check for
     paywall artefacts that would mean the paid subscription isn't being used.

Screenshots: /tmp/explore_*.png
Run: ~/yt-pw/bin/python tools/news_explore.py
"""
import os
import re
import time
from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/news-pw-profile")
REAL_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/126.0.0.0 Safari/537.36")


def shot(page, name):
    try:
        page.screenshot(path=f"/tmp/explore_{name}.png")
        print(f"    [shot] /tmp/explore_{name}.png", flush=True)
    except Exception:
        pass


# Phrases that indicate the article is still behind a paywall.
NIKKEI_PAYWALL_PHRASES = ("この記事は会員限定", "有料会員限定", "会員登録",
                          "続きを読むには", "ログインしてください")
BBG_PAYWALL_PHRASES = ("Subscribe to read", "Get Unlimited Access",
                       "サブスクリプション", "有料記事", "Subscribe Now")


def first_article_href(page, base_selectors):
    """Find the first plausible article link on the current page."""
    for sel in base_selectors:
        try:
            els = page.locator(sel).all()
            for el in els[:15]:
                href = el.get_attribute("href") or ""
                if not href:
                    continue
                if any(skip in href for skip in ("/topic/", "/markets/$", "/about", "javascript:",
                                                "/account/", "/news/category", "/markets/?")):
                    continue
                return href
        except Exception:
            continue
    return None


def has_phrase(page, phrases):
    try:
        body = (page.locator("body").inner_text() or "").lower()
    except Exception:
        return None
    body_lc = body
    found = [p for p in phrases if p.lower() in body_lc]
    return found


def explore_nikkei(page):
    print("\n=== Nikkei ===", flush=True)
    print("  -> homepage", flush=True)
    page.goto("https://www.nikkei.com/", wait_until="load", timeout=60000)
    time.sleep(4)
    shot(page, "n1_home")
    login_btn = page.query_selector('a:has-text("ログイン"), button:has-text("ログイン")')
    print(f"    login button visible: {bool(login_btn and login_btn.is_visible())}", flush=True)
    # category: 株/マーケット
    print("  -> markets page", flush=True)
    page.goto("https://www.nikkei.com/markets/", wait_until="load", timeout=60000)
    time.sleep(4)
    shot(page, "n2_markets")
    # find first article link inside a /article/ or news path
    href = first_article_href(page, [
        'a[href*="/article/"]', 'a[href*="/news/"]',
        'a[href*="/nikkei-article/"]',
    ])
    print(f"    first article: {href}", flush=True)
    if href:
        if href.startswith("/"):
            href = "https://www.nikkei.com" + href
        page.goto(href, wait_until="load", timeout=60000)
        time.sleep(5)
        shot(page, "n3_article")
        paywall = has_phrase(page, NIKKEI_PAYWALL_PHRASES)
        print(f"    paywall phrases found: {paywall or '(none — likely full access)'}", flush=True)
        # length check as additional signal
        try:
            text_len = len(page.locator("article").first.inner_text())
        except Exception:
            text_len = len(page.locator("body").inner_text() or "")
        print(f"    article text length: {text_len} chars", flush=True)


def explore_bloomberg(page):
    print("\n=== Bloomberg ===", flush=True)
    print("  -> homepage (jp)", flush=True)
    page.goto("https://www.bloomberg.co.jp/", wait_until="load", timeout=90000)
    time.sleep(5)
    shot(page, "b1_home")
    login_link = page.query_selector('a:has-text("ログイン")')
    print(f"    ログイン visible: {bool(login_link and login_link.is_visible())}", flush=True)
    # category: マーケット
    for url, label in [
        ("https://www.bloomberg.co.jp/markets", "b2_markets"),
        ("https://www.bloomberg.co.jp/technology", "b3_tech"),
    ]:
        print(f"  -> {url}", flush=True)
        try:
            page.goto(url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"    ! goto failed: {str(e)[:120]}", flush=True); continue
        time.sleep(4)
        shot(page, label)
    # try opening the first article on the markets page
    page.goto("https://www.bloomberg.co.jp/markets", wait_until="load", timeout=60000)
    time.sleep(4)
    href = first_article_href(page, [
        'a[href*="/news/articles/"]', 'a[href*="/news/features/"]',
        'a[href*="/articles/"]',
    ])
    print(f"    first article: {href}", flush=True)
    if href:
        if href.startswith("/"):
            href = "https://www.bloomberg.co.jp" + href
        try:
            page.goto(href, wait_until="load", timeout=90000)
        except Exception as e:
            print(f"    ! article goto failed: {str(e)[:120]}", flush=True); return
        time.sleep(6)
        shot(page, "b4_article")
        paywall = has_phrase(page, BBG_PAYWALL_PHRASES)
        print(f"    paywall phrases: {paywall or '(none — likely full access)'}", flush=True)
        try:
            text_len = len(page.locator("article").first.inner_text())
        except Exception:
            text_len = len(page.locator("body").inner_text() or "")
        print(f"    article text length: {text_len} chars", flush=True)


def main() -> int:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True, user_agent=REAL_UA, locale="ja-JP",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            explore_nikkei(page)
        except Exception as e:
            print(f"  ! Nikkei exception: {str(e)[:200]}", flush=True)
        try:
            explore_bloomberg(page)
        except Exception as e:
            print(f"  ! Bloomberg exception: {str(e)[:200]}", flush=True)
        time.sleep(3)
        ctx.close()
    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
