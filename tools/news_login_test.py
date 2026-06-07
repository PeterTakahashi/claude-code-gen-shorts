#!/usr/bin/env python3
"""Verify Nikkei + Bloomberg paid logins, saving the session to a persistent
Playwright profile so later fetches can reuse the authenticated cookies.

Reads NIKKEI_EMAIL/PASSWORD and BLOOMBERG_EMAIL/PASSWORD from .env (values are
never printed). Headed Chromium so the user can intervene on a CAPTCHA. Each
site reports OK/FAIL based on the absence of a "ログイン" / "Sign In" button on
the homepage after the flow.

Run:  ~/yt-pw/bin/python tools/news_login_test.py
"""
import os
import sys
import time
from pathlib import Path

from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = "/Users/apple/dev/claude-code/webtoon-gen"
PROFILE = os.path.expanduser("~/news-pw-profile")
env = dotenv_values(f"{ROOT}/.env")


def shot(page, name):
    try:
        page.screenshot(path=f"/tmp/news_{name}.png")
        print(f"  [shot] /tmp/news_{name}.png", flush=True)
    except Exception:
        pass


def try_fill(page, selectors, value, timeout=10000) -> bool:
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def try_click(page, selectors, timeout=8000) -> bool:
    for sel in selectors:
        try:
            page.click(sel, timeout=timeout)
            return True
        except Exception:
            continue
    return False


def login_nikkei(page) -> tuple[bool, str]:
    """Nikkei is a strict 2-step: email -> 次に進む -> password -> 次に進む."""
    email = env.get("NIKKEI_EMAIL")
    pw = env.get("NIKKEI_PASSWORD")
    if not email or not pw:
        return False, "creds missing in .env"
    print("\n>>> Nikkei login", flush=True)
    try:
        page.goto("https://www.nikkei.com/", wait_until="load", timeout=60000)
    except Exception as e:
        return False, f"home goto failed: {str(e)[:120]}"
    time.sleep(5)
    shot(page, "0_nikkei_home_before")
    # already logged in? (persistent profile may have a live session)
    login_btn = page.query_selector('a:has-text("ログイン"), button:has-text("ログイン")')
    if not (login_btn and login_btn.is_visible()):
        return True, "already logged in (no ログイン button on home)"
    # click ログイン on the home page (avoids direct-URL WAF)
    try:
        page.get_by_text("ログイン", exact=False).first.click(timeout=10000)
    except Exception:
        return False, "ログイン link not found on homepage"
    try:
        page.wait_for_url("**id.nikkei.com/**", timeout=20000)
    except Exception:
        pass
    time.sleep(4)
    shot(page, "1_nikkei_email_step")
    # STEP 1: email
    try:
        page.fill('input[type="email"]', email, timeout=15000)
    except Exception as e:
        return False, f"email fill failed: {str(e)[:120]}"
    print("  email filled", flush=True)
    try:
        page.click('button:has-text("次に進む")', timeout=8000)
    except Exception:
        try_click(page, ['button[type="submit"]', 'input[type="submit"]'])
    # STEP 2: wait for password field then fill
    try:
        page.wait_for_selector('input[type="password"]', timeout=20000, state="visible")
    except Exception:
        shot(page, "1b_nikkei_no_pwd")
        return False, "password field never appeared"
    time.sleep(1)
    shot(page, "1c_nikkei_pwd_step")
    try:
        page.fill('input[type="password"]', pw, timeout=10000)
    except Exception as e:
        return False, f"password fill failed: {str(e)[:120]}"
    print("  password filled", flush=True)
    try:
        page.click('button:has-text("次に進む")', timeout=8000)
    except Exception:
        try_click(page, ['button[type="submit"]', 'input[type="submit"]'])
    # wait for navigation away from id.nikkei.com (successful login redirects back)
    try:
        page.wait_for_url(lambda u: "id.nikkei.com" not in u, timeout=20000)
        print(f"  navigated to: {page.url[:80]}", flush=True)
    except Exception:
        print(f"  still on: {page.url[:80]}", flush=True)
    time.sleep(4)
    shot(page, "2_nikkei_after_submit")
    page.goto("https://www.nikkei.com/", wait_until="load", timeout=60000)
    time.sleep(3)
    shot(page, "3_nikkei_home")
    login_btn = page.query_selector('a:has-text("ログイン"), button:has-text("ログイン")')
    login_btn_visible = bool(login_btn and login_btn.is_visible())
    mypage = page.query_selector(
        'a[href*="/mypage"], a:has-text("マイページ"), a:has-text("マイニュース")')
    if mypage and not login_btn_visible:
        return True, "logged in (mypage link present, no ログイン button)"
    if not login_btn_visible:
        return True, "no ログイン button visible"
    return False, "still seeing ログイン button on home (auth likely rejected — wrong pw, CAPTCHA, or 2FA)"


def login_bloomberg(page) -> tuple[bool, str]:
    """Bloomberg.co.jp (JP locale auto-redirects from .com under ja-JP UA)."""
    email = env.get("BLOOMBERG_EMAIL")
    pw = env.get("BLOOMBERG_PASSWORD")
    if not email or not pw:
        return False, "creds missing in .env"
    print("\n>>> Bloomberg login", flush=True)
    try:
        page.goto("https://www.bloomberg.co.jp/", wait_until="load", timeout=90000)
    except Exception as e:
        return False, f"home goto failed: {str(e)[:120]}"
    time.sleep(6)
    shot(page, "3_bbg_home_before")
    # Cookie consent: the banner is "Cookieに関するお客さまの選択" with a "同意する"
    # button. Without dismissing it, its overlay blocks clicks on ログイン.
    consent_done = False
    for try_idx in range(3):
        try:
            page.get_by_text("同意する", exact=True).first.click(timeout=4000)
            consent_done = True
            print("  cookie consent: clicked 同意する", flush=True); break
        except Exception:
            pass
        try:
            page.locator('button:has-text("同意する"), [role="button"]:has-text("同意する")').first.click(timeout=3000)
            consent_done = True
            print("  cookie consent: clicked via role-button", flush=True); break
        except Exception:
            pass
        time.sleep(2)
    if not consent_done:
        print("  ⚠ cookie consent button not found (banner may not be present)", flush=True)
    # wait for the banner to actually disappear
    try:
        page.wait_for_selector('text=Cookieに関するお客さま', state="hidden", timeout=8000)
    except Exception:
        pass
    time.sleep(2)
    shot(page, "3b_bbg_after_consent")
    # Get the login link's href and navigate directly (clicking the link can
    # be eaten by the SPA or open a popup that we don't follow).
    login_href = None
    try:
        link = page.locator('a:has-text("ログイン")').first
        login_href = link.get_attribute("href")
        print(f"  ログイン href: {login_href}", flush=True)
    except Exception:
        pass
    if login_href:
        # absolute or relative
        if login_href.startswith("/"):
            login_href = "https://www.bloomberg.co.jp" + login_href
        try:
            page.goto(login_href, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"  ! goto login href failed: {str(e)[:120]}", flush=True)
    else:
        # fallback: try a known Bloomberg login URL
        try:
            page.goto("https://account.bloomberg.com/account/signin",
                      wait_until="load", timeout=60000)
        except Exception as e:
            return False, f"could not navigate to a login URL: {str(e)[:120]}"
    time.sleep(6)
    shot(page, "4_bbg_form")
    print(f"  now at: {page.url[:100]}", flush=True)
    if not try_fill(page,
                    ['input[type="email"]', 'input[name="email"]', 'input#email',
                     'input[autocomplete="username"]'],
                    email, timeout=20000):
        return False, "email field not found (likely PerimeterX block — see screenshot)"
    print("  email filled", flush=True)
    if not try_fill(page,
                    ['input[type="password"]', 'input[name="password"]',
                     'input#password'],
                    pw, timeout=6000):
        try_click(page,
                  ['button[type="submit"]', 'button:has-text("Continue")',
                   'button:has-text("Next")'])
        time.sleep(3)
        if not try_fill(page,
                        ['input[type="password"]', 'input[name="password"]'],
                        pw, timeout=10000):
            shot(page, "4b_bbg_no_pwd")
            return False, "password field not found after email step"
    print("  password filled", flush=True)
    try_click(page,
              ['button[type="submit"]', 'button:has-text("Sign In")',
               'button:has-text("Log In")'])
    time.sleep(8)
    shot(page, "5_bbg_after_submit")
    page.goto("https://www.bloomberg.com/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    shot(page, "6_bbg_home")
    signin = page.query_selector('a[href*="signin"], button:has-text("Sign In")')
    signin_visible = bool(signin and signin.is_visible())
    account = page.query_selector('button[aria-label*="Account" i], a[href*="/account"]')
    if account and not signin_visible:
        return True, "logged in (account control present, no Sign In)"
    if not signin_visible:
        return True, "no Sign In button visible (assumed logged in)"
    return False, "still seeing Sign In on home"


def main() -> int:
    if not env.get("NIKKEI_EMAIL") or not env.get("BLOOMBERG_EMAIL"):
        print("ERROR: missing NIKKEI_/BLOOMBERG_ credentials in .env", file=sys.stderr)
        return 1
    os.makedirs(PROFILE, exist_ok=True)
    REAL_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/126.0.0.0 Safari/537.36")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True, user_agent=REAL_UA, locale="ja-JP",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        results = []
        for site, fn in [("Nikkei", login_nikkei), ("Bloomberg", login_bloomberg)]:
            try:
                ok, note = fn(page)
            except Exception as e:
                ok, note = False, f"exception: {str(e)[:200]}"
            results.append((site, ok, note))
            print(f"  -> {site}: {'OK' if ok else 'FAIL'} — {note}", flush=True)
        ctx.close()
    print("\n===== SUMMARY =====")
    for s, ok, note in results:
        print(f"  [{'OK' if ok else 'FAIL'}] {s}: {note}")
    return 0 if all(r[1] for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
