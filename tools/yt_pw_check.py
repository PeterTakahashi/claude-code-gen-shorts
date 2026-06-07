#!/usr/bin/env python3
"""Reuse the saved Playwright profile to confirm login + per-channel access.

Opens YouTube Studio (default + a specific channel context by UC id) and
screenshots, to verify the persistent session works for uploads.

Run: ~/yt-pw/bin/python tools/yt_pw_check.py <UC_CHANNEL_ID>
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/yt-pw-profile")


def main() -> int:
    ch = sys.argv[1] if len(sys.argv) > 1 else None
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        print(f"default studio url: {page.url}", flush=True)
        page.screenshot(path="/tmp/yt_default.png")
        # current channel name (top-left in studio)
        try:
            name = page.query_selector('#channel-title, #entity-name, ytcp-channel-info #title')
            print("channel name elem:", name.inner_text().strip() if name else "(not found)", flush=True)
        except Exception as e:
            print("name note:", str(e)[:120], flush=True)
        if ch:
            page.goto(f"https://studio.youtube.com/channel/{ch}", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            print(f"channel-context url: {page.url}", flush=True)
            page.screenshot(path="/tmp/yt_channel.png")
        time.sleep(2)
        ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
