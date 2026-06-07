#!/usr/bin/env python3
"""Delete a video from a specific channel via YouTube Studio (Playwright).

Switches to the target Brand Account (channel_switcher), verifies the channel id,
opens the video's edit page, then Options -> "Delete forever" -> confirm.

Usage:
  ~/yt-pw/bin/python tools/yt_pw_delete.py "<channel display name>" <UC_channel_id> <video_id>

Screenshots to /tmp/del_*.png. Headed.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/yt-pw-profile")


def shot(page, name):
    try:
        page.screenshot(path=f"/tmp/del_{name}.png")
        print(f"  [shot] /tmp/del_{name}.png", flush=True)
    except Exception:
        pass


def click_text(page, texts, timeout=12000, role=None):
    for t in texts:
        try:
            loc = page.get_by_role(role, name=t).first if role else page.get_by_text(t, exact=False).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            print(f"  clicked: {t}", flush=True)
            return True
        except Exception:
            continue
    return False


def main() -> int:
    channel_name, uc_id, vid = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f"delete {vid} on {channel_name} ({uc_id})", flush=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 1) switch channel
        page.goto("https://www.youtube.com/channel_switcher?themeRefresh=1",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        if not click_text(page, [channel_name], timeout=20000):
            print("  !! channel not found in switcher", flush=True)
            shot(page, "noswitch"); ctx.close(); return 2
        time.sleep(6)

        # 2) open the video edit page (channel context now set)
        page.goto(f"https://studio.youtube.com/video/{vid}/edit",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        print("  url:", page.url, flush=True)
        if uc_id not in page.url and "/video/" not in page.url:
            print(f"  !! unexpected url (channel/permission?) — aborting", flush=True)
            shot(page, "badurl"); ctx.close(); return 3
        shot(page, "1_edit")

        # 3) Options menu (top-right ⋮) -> Delete forever
        opened = False
        for sel in ('#options-button', 'ytcp-icon-button#options-button',
                    'ytcp-button#options-button', 'button[aria-label="Options"]',
                    'ytcp-icon-button[aria-label="Options"]'):
            try:
                page.click(sel, timeout=4000); opened = True
                print(f"  opened options via {sel}", flush=True); break
            except Exception:
                continue
        if not opened:
            try:
                page.get_by_role("button", name="Options").first.click(timeout=6000); opened = True
            except Exception:
                pass
        time.sleep(1.8)
        shot(page, "2_optionsmenu")

        # the dropdown is a paper-listbox; click the "Delete forever" item
        clicked = False
        for sel in ('tp-yt-paper-item:has-text("Delete forever")',
                    'tp-yt-paper-item:has-text("完全に削除")',
                    'ytcp-text-menu tp-yt-paper-item:has-text("Delete")',
                    '*:has-text("Delete forever")'):
            try:
                page.click(sel, timeout=4000); clicked = True
                print(f"  clicked delete via {sel}", flush=True); break
            except Exception:
                continue
        if not clicked:
            clicked = click_text(page, ["Delete forever", "完全に削除", "完全に削除する"], timeout=6000)
        if not clicked:
            print("  !! 'Delete forever' menu item not found", flush=True)
            shot(page, "2b_nodelete"); ctx.close(); return 4
        time.sleep(2)
        shot(page, "3_confirm_dialog")

        # 4) confirm: tick the acknowledgement checkbox, then the Delete button
        try:
            cb = page.query_selector('ytcp-checkbox-lit, #checkbox, tp-yt-paper-checkbox')
            if cb:
                cb.click(); print("  checked acknowledgement", flush=True); time.sleep(0.6)
        except Exception:
            pass
        # the confirm button in the dialog
        done = False
        for sel in ('#confirm-button', 'ytcp-button#confirm-button'):
            el = page.query_selector(sel)
            if el and el.is_enabled():
                el.click(); done = True; print(f"  confirmed via {sel}", flush=True); break
        if not done:
            click_text(page, ["Delete forever", "完全に削除", "削除"], timeout=6000, role="button")
        time.sleep(5)
        shot(page, "4_after_delete")
        print("DONE", flush=True)
        time.sleep(2)
        ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
