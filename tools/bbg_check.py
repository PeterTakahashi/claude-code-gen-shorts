#!/usr/bin/env python3
"""Check Bloomberg login state on both .com (US/EN) and .co.jp (JP), then
open one Markets article on whichever is logged in to verify paywall bypass.

Run: ~/yt-pw/bin/python tools/bbg_check.py
"""
import os
import time
from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/news-pw-profile")
REAL_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/126.0.0.0 Safari/537.36")


def shot(page, name):
    try:
        page.screenshot(path=f"/tmp/bbgchk_{name}.png")
        print(f"    [shot] /tmp/bbgchk_{name}.png", flush=True)
    except Exception:
        pass


def check_state(page, url, label, login_text, sign_in_text):
    print(f"\n>>> {label}  {url}", flush=True)
    try:
        page.goto(url, wait_until="load", timeout=60000)
    except Exception as e:
        print(f"  ! goto failed: {str(e)[:120]}", flush=True); return False
    time.sleep(5)
    shot(page, label)
    # search for either Japanese ログイン or English Sign In
    has_login_jp = bool(page.query_selector(f'a:has-text("{login_text}")'))
    has_signin_en = bool(page.query_selector(f'a:has-text("{sign_in_text}")'))
    has_account = bool(page.query_selector('a[href*="/account"], button[aria-label*="Account" i]'))
    print(f"    {login_text} link: {has_login_jp}   '{sign_in_text}' link: {has_signin_en}   account ctrl: {has_account}", flush=True)
    return not (has_login_jp or has_signin_en) or has_account


def first_article(page, sels):
    for sel in sels:
        try:
            els = page.locator(sel).all()
            for el in els[:20]:
                href = (el.get_attribute("href") or "").strip()
                if "/news/articles/" in href or "/news/features/" in href:
                    return href
        except Exception:
            continue
    return None


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True, user_agent=REAL_UA, locale="en-US",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # 1. US Bloomberg
        us_logged_in = check_state(page, "https://www.bloomberg.com/", "us_home",
                                    "ログイン", "Sign In")
        # 2. JP Bloomberg
        jp_logged_in = check_state(page, "https://www.bloomberg.co.jp/", "jp_home",
                                    "ログイン", "Sign In")
        # 3. Try a Markets article — try US first, fall back to JP
        for base, label in [
            ("https://www.bloomberg.com/markets", "us_markets"),
            ("https://www.bloomberg.co.jp/markets", "jp_markets"),
        ]:
            print(f"\n>>> Markets at {base}", flush=True)
            try:
                page.goto(base, wait_until="load", timeout=60000)
            except Exception as e:
                print(f"  ! goto failed: {str(e)[:120]}", flush=True); continue
            time.sleep(5)
            shot(page, label)
            href = first_article(page, ['a[href*="/news/articles/"]', 'a[href*="/news/features/"]'])
            print(f"    first article: {href}", flush=True)
            if href:
                if href.startswith("/"):
                    host = "https://www.bloomberg.co.jp" if "co.jp" in base else "https://www.bloomberg.com"
                    href = host + href
                try:
                    page.goto(href, wait_until="load", timeout=90000)
                    time.sleep(7)
                    shot(page, label + "_article")
                    body = (page.locator("body").inner_text() or "")
                    paywall_phrases = ["Subscribe to read", "Get Unlimited Access",
                                       "Subscribe Now", "サブスクリプション", "有料記事"]
                    found = [p for p in paywall_phrases if p.lower() in body.lower()]
                    print(f"    article body len: {len(body)}   paywall phrases: {found or '(none)'}", flush=True)
                    break  # don't open second article
                except Exception as e:
                    print(f"  ! article goto failed: {str(e)[:120]}", flush=True)
        time.sleep(3)
        ctx.close()
    print("\nDONE")


if __name__ == "__main__":
    raise SystemExit(main())
