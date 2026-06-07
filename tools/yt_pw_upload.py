#!/usr/bin/env python3
"""Upload a webtoon short to a specific channel via YouTube Studio (Playwright, quota-free).

Why: the YouTube Data API enforces a *daily* video-upload cap (~10-12/day) that
blocks our backlog. Browser upload through Studio is not subject to that cap.

Flow: channel_switcher -> click target Brand Account -> Studio -> Create ->
Upload videos -> set file -> title/description -> Next x3 -> Public -> Publish.
On success, records the short in projects/<id>/.youtube_shorts_uploads.json so
the API-based paced uploader (tools/upload_paced.py) skips it (no double upload).

Metadata is read from the short yaml exactly like src.youtube_batch_upload_shorts
(v2 `ja:` section first, then top-level), so titles/descriptions match.

Usage:
  ~/yt-pw/bin/python tools/yt_pw_upload.py <project_id> <short_id> "<channel display name>" [--dry-run]

--dry-run stops before Publish (leaves a private draft you can inspect/delete).
Screenshots each step to /tmp/up_*.png. Headed.
"""
import datetime
import json
import os
import sys
import time

import yaml
from playwright.sync_api import sync_playwright

ROOT = "/Users/apple/dev/claude-code/webtoon-gen"
PROFILE = os.path.expanduser("~/yt-pw-profile")


def shot(page, name):
    try:
        page.screenshot(path=f"/tmp/up_{name}.png")
        print(f"  [shot] /tmp/up_{name}.png", flush=True)
    except Exception:
        pass


def click_text(page, texts, timeout=15000, role=None):
    """Click the first visible element matching any of the given texts (JA/EN)."""
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


def load_meta(project_id: str, short_id: str, lang: str = "ja"):
    yml = f"{ROOT}/projects/{project_id}/shorts/{short_id}.yaml"
    cfg = yaml.safe_load(open(yml, encoding="utf-8"))

    def lf(field):
        sec = cfg.get(lang)
        if isinstance(sec, dict) and field in sec:
            return sec[field]
        return cfg.get(field, "")

    title = lf("title") or cfg.get("title", "")
    desc = lf("description") or cfg.get("description", "")
    video = f"{ROOT}/projects/{project_id}/output/shorts/{short_id}/{lang}/short.mp4"
    return title, desc, video


def record_upload(project_id: str, short_id: str, title: str, video_id: str):
    """Mark the short as uploaded so the API paced uploader skips it."""
    log_path = f"{ROOT}/projects/{project_id}/.youtube_shorts_uploads.json"
    try:
        log = json.load(open(log_path, encoding="utf-8"))
    except Exception:
        log = {"uploads": {}}
    log.setdefault("uploads", {})[short_id] = {
        "video_id": video_id,
        "title": title,
        "via": "playwright",
        "ts": datetime.datetime.utcnow().isoformat(),
    }
    json.dump(log, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  recorded in log: {short_id} -> {video_id}", flush=True)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    project_id, short_id, channel_name = args[0], args[1], args[2]
    expect_uc = args[3] if len(args) > 3 else ""  # expected UC channel id for safety
    title, desc, video = load_meta(project_id, short_id)
    if not title:
        print("ERROR: no title in yaml", file=sys.stderr); return 1
    if not os.path.isfile(video):
        print(f"ERROR: video not found: {video}", file=sys.stderr); return 1
    print(f"project={project_id} short={short_id} channel={channel_name} dry={dry}", flush=True)
    print(f"title: {title}", flush=True)
    print(f"video: {video}", flush=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 1) switch to the target channel via channel_switcher
        print(f">>> switch channel: {channel_name}", flush=True)
        page.goto("https://www.youtube.com/channel_switcher?themeRefresh=1",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        shot(page, "1_switcher")
        if not click_text(page, [channel_name], timeout=20000):
            print("  !! could not find channel in switcher", flush=True)
            shot(page, "1b_noswitch"); ctx.close(); return 2
        time.sleep(6)
        shot(page, "2_after_switch")

        # 2) go to Studio
        page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        print("  studio url:", page.url, flush=True)
        shot(page, "3_studio")

        # 2b) SAFETY: confirm we landed on the intended channel before uploading.
        if expect_uc and expect_uc not in page.url:
            print(f"  !! WRONG CHANNEL — url has no {expect_uc}; aborting to avoid misupload", flush=True)
            shot(page, "3b_wrongchan"); ctx.close(); return 4

        # 3) Create -> Upload videos.
        # NOTE: on brand-new (0-video) channels the dashboard also shows a big
        # center "Upload videos" button that opens a NATIVE OS file picker
        # (Playwright can't set_input_files on it). So target the Create dropdown
        # MENU ITEM specifically (tp-yt-paper-item), which opens the in-page
        # dialog with a hidden input[type=file].
        click_text(page, ["作成", "Create"], timeout=20000)
        time.sleep(2)
        picked = False
        for sel in ('tp-yt-paper-item:has-text("Upload videos")',
                    'tp-yt-paper-item:has-text("動画をアップロード")',
                    'ytcp-text-menu tp-yt-paper-item:has-text("Upload")',
                    'yt-formatted-string:has-text("Upload videos")'):
            try:
                page.click(sel, timeout=4000); picked = True
                print(f"  clicked upload-videos via {sel}", flush=True); break
            except Exception:
                continue
        if not picked:
            click_text(page, ["動画をアップロード", "Upload videos"], timeout=8000)
        time.sleep(4)
        shot(page, "4_upload_dialog")

        # 4) set the file on the hidden input
        try:
            page.set_input_files('input[type="file"]', video)
            print("  file set:", video, flush=True)
        except Exception as e:
            print("  !! file input error:", str(e)[:160], flush=True)
            shot(page, "4b_nofileinput"); ctx.close(); return 3
        time.sleep(12)
        shot(page, "5_uploading")

        # 4b) Capture the REAL video id NOW, from the wizard's "Video link" field.
        # (After publish the dashboard is visible and link-scraping grabs the wrong
        # video; during the wizard the only youtu.be link is this upload's.)
        captured_id = ""
        try:
            for sel in ('ytcp-video-info a[href*="youtu.be/"]',
                        'a.ytcp-video-info[href*="youtu.be/"]',
                        'a[href*="youtu.be/"]', 'a[href*="/shorts/"]'):
                el = page.query_selector(sel)
                if el:
                    href = el.get_attribute("href") or ""
                    for sep in ("youtu.be/", "/shorts/", "watch?v="):
                        if sep in href:
                            captured_id = href.split(sep)[1].split("?")[0].split("&")[0].strip()
                            break
                if captured_id:
                    print(f"  captured video id: {captured_id}", flush=True)
                    break
        except Exception as e:
            print("  id-capture note:", str(e)[:140], flush=True)

        # 5) title + description (Details step). Studio prefills title from filename.
        try:
            boxes = page.query_selector_all('#textbox')
            print(f"  found {len(boxes)} #textbox elements", flush=True)
            if boxes:
                boxes[0].click(); time.sleep(0.4)
                # macOS: select-all is Cmd/Meta+A (Ctrl+A does NOT select-all here),
                # so clear the filename prefill before typing the real title.
                page.keyboard.press("Meta+A"); page.keyboard.press("Delete"); time.sleep(0.3)
                page.keyboard.insert_text(title[:99])
                print("  title set", flush=True)
            if len(boxes) >= 2 and desc:
                boxes[1].click(); time.sleep(0.3)
                page.keyboard.insert_text(desc[:480])
                print("  description set", flush=True)
        except Exception as e:
            print("  title/desc note:", str(e)[:160], flush=True)

        # 5b) "Made for kids?" is REQUIRED — answer "No" or Next stays disabled.
        try:
            mfk = page.query_selector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]')
            if mfk:
                mfk.click(); print("  made-for-kids: No", flush=True)
            elif click_text(page, ["No, it's not made for kids", "いいえ、子ども向けではありません",
                                    "子ども向けではありません", "No, it's not"], timeout=6000):
                print("  made-for-kids: No (text)", flush=True)
            else:
                print("  !! made-for-kids radio not found", flush=True)
        except Exception as e:
            print("  made-for-kids note:", str(e)[:160], flush=True)
        time.sleep(0.5)
        shot(page, "6_details")

        # 6) Advance Details -> Video elements -> Checks -> Visibility using the
        # stable #next-button id; stop once the PUBLIC visibility radio appears.
        for i in range(6):
            if page.query_selector('tp-yt-paper-radio-button[name="PUBLIC"]'):
                print("  reached Visibility step", flush=True); break
            nb = page.query_selector('#next-button')
            if nb and nb.is_enabled():
                nb.click(); print(f"  next #{i+1}", flush=True)
            else:
                print(f"  next #{i+1}: button missing/disabled", flush=True)
            time.sleep(2.5)
            shot(page, f"7_step{i+1}")

        # 7) Visibility = Public
        pub = page.query_selector('tp-yt-paper-radio-button[name="PUBLIC"]')
        if pub:
            pub.click(); print("  visibility: Public", flush=True)
        else:
            click_text(page, ["公開 (Public)", "Public", "公開"], timeout=6000, role="radio")
        time.sleep(1)
        shot(page, "8_visibility")

        if dry:
            print("DRY RUN — stopping before Publish (draft left as private).", flush=True)
            shot(page, "9_dry_stop")
            time.sleep(3); ctx.close(); return 0

        # 8) Publish (stable #done-button)
        done = page.query_selector('#done-button')
        if done and done.is_enabled():
            done.click(); print("  clicked Publish (#done-button)", flush=True)
        else:
            click_text(page, ["公開", "Publish", "Done", "保存"], timeout=8000, role="button")
        time.sleep(4)
        shot(page, "9a_after_publish")

        # 8b) Freshly-uploaded videos may still be running content checks, which
        # raises a "We're still checking your content — Publish anyway?" dialog.
        # Confirm it (our content is original; the warning is boilerplate).
        try:
            if click_text(page, ["Publish anyway", "今すぐ公開", "このまま公開", "公開する"],
                          timeout=6000, role="button"):
                print("  confirmed: Publish anyway", flush=True)
                time.sleep(5)
        except Exception:
            pass
        # Wait for the "Video published" confirmation dialog as a success signal.
        try:
            page.wait_for_selector('ytcp-video-info, ytcp-uploads-still-processing-dialog, #share-url',
                                   timeout=20000)
        except Exception:
            pass
        time.sleep(4)
        shot(page, "9_published")

        # Prefer the id captured from the wizard (reliable); only fall back to a
        # post-publish scrape if capture failed (less reliable: dashboard links).
        video_id = captured_id
        if not video_id:
            try:
                link = page.query_selector('ytcp-video-info a[href*="youtu.be/"], a[href*="youtu.be/"], a[href*="/shorts/"]')
                href = (link.get_attribute("href") or "") if link else ""
                for sep in ("youtu.be/", "/shorts/", "watch?v="):
                    if sep in href:
                        video_id = href.split(sep)[1].split("&")[0].split("?")[0].strip()
                        break
            except Exception:
                pass
        print(f"  published video id: {video_id or '(unknown)'}  https://youtube.com/shorts/{video_id}", flush=True)
        record_upload(project_id, short_id, title, video_id or f"pw_{int(time.time())}")
        print("DONE", flush=True)
        time.sleep(3)
        ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
