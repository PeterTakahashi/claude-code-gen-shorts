#!/usr/bin/env python3
"""List the YouTube channels (Brand Accounts) switchable from the logged-in account."""
import os
import time
from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/yt-pw-profile")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE, headless=False,
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        no_viewport=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.youtube.com/channel_switcher", wait_until="domcontentloaded", timeout=60000)
    time.sleep(6)
    print("url:", page.url, flush=True)
    page.screenshot(path="/tmp/yt_switcher.png", full_page=True)
    # try to read channel names/links
    try:
        items = page.query_selector_all('a[href*="channel_switcher"], #contents ytd-account-item-renderer, yt-formatted-string#channel-title, #channel-title')
        names = []
        for el in items:
            t = (el.inner_text() or "").strip()
            if t:
                names.append(t)
        print("found texts:", names[:40], flush=True)
    except Exception as e:
        print("read note:", str(e)[:160], flush=True)
    time.sleep(2)
    ctx.close()
