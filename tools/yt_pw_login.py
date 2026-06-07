#!/usr/bin/env python3
"""Log into Google/YouTube in a persistent Playwright Chromium profile.

Headed browser: fills GOOGLE_EMAIL/GOOGLE_PASSWORD from .env, then WAITS for you
to complete any 2FA / "verify it's you" challenge in the window that opens.
On success the session is saved to the persistent profile dir so later upload
runs reuse it (no re-login). Credentials are never printed.

Run:  ~/yt-pw/bin/python tools/yt_pw_login.py
"""
import os
import sys
import time
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = "/Users/apple/dev/claude-code/webtoon-gen"
PROFILE = os.path.expanduser("~/yt-pw-profile")
env = dotenv_values(f"{ROOT}/.env")
EMAIL = env.get("GOOGLE_EMAIL")
PASSWORD = env.get("GOOGLE_PASSWORD")


def is_logged_in(page) -> bool:
    try:
        page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        # the "Sign in" link is only present when logged OUT
        signin = page.query_selector('a[aria-label="Sign in"], ytd-button-renderer:has-text("Sign in"), a:has-text("ログイン")')
        avatar = page.query_selector('button#avatar-btn, #avatar-btn')
        return avatar is not None and signin is None
    except Exception:
        return False


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("ERROR: GOOGLE_EMAIL / GOOGLE_PASSWORD not set in .env", file=sys.stderr)
        return 1
    os.makedirs(PROFILE, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if is_logged_in(page):
            print("ALREADY_LOGGED_IN", flush=True)
        else:
            print("logging in (filling email/password)…", flush=True)
            page.goto("https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fstudio.youtube.com",
                      wait_until="domcontentloaded", timeout=60000)
            try:
                page.fill('input[type="email"]', EMAIL, timeout=20000)
                page.click('#identifierNext, button:has-text("Next"), button:has-text("次へ")')
                page.wait_for_timeout(3000)
                page.fill('input[type="password"]', PASSWORD, timeout=30000)
                page.click('#passwordNext, button:has-text("Next"), button:has-text("次へ")')
                print("submitted credentials — COMPLETE ANY 2FA / verification IN THE BROWSER WINDOW now…", flush=True)
            except Exception as e:
                print(f"login form step note: {str(e)[:160]}", flush=True)
                print("If Google shows a challenge/CAPTCHA, complete it in the window.", flush=True)
            # Poll up to 4 minutes for login to complete (user does 2FA).
            deadline = time.time() + 240
            ok = False
            while time.time() < deadline:
                time.sleep(8)
                if is_logged_in(page):
                    ok = True
                    break
                print(f"  …waiting for login ({int(deadline - time.time())}s left)", flush=True)
            print("LOGIN_OK" if ok else "LOGIN_TIMEOUT", flush=True)

        # report what channel/account we're on
        try:
            page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            page.screenshot(path="/tmp/yt_studio.png", full_page=False)
            print(f"studio url: {page.url}", flush=True)
            print("screenshot: /tmp/yt_studio.png", flush=True)
        except Exception as e:
            print(f"studio nav note: {str(e)[:160]}", flush=True)
        ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
