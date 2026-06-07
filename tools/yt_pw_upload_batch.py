#!/usr/bin/env python3
"""Publish the pending shorts backlog to their channels via Studio (Playwright).

Runs tools/yt_pw_upload.py once per video (fresh browser each time for isolation:
one stuck upload can't poison the rest). Sequential with a gap between uploads to
avoid burst-rate flags. Pass short_ids as args to filter; default = all rows.

Run:  ~/yt-pw/bin/python tools/yt_pw_upload_batch.py [short_id ...]
"""
import subprocess
import sys
import time

ROOT = "/Users/apple/dev/claude-code/webtoon-gen"
PYBIN = "/Users/apple/yt-pw/bin/python"
SCRIPT = f"{ROOT}/tools/yt_pw_upload.py"

# (project_id, short_id, channel_display_name, expected_UC_channel_id)
ROWS = [
    ("tadashiyanai",   "yanai-uk-failure",          "偉人伝",                       "UCSJvtb0ZJg6P6X8QIweBsRA"),
    ("sports_legends", "sports-hanyu-2peat",         "バルトゥーンスポーツ選手伝説", "UCjAvJkRe2mcTJWpKz3zZcEA"),
    ("sports_legends", "sports-oh-868",              "バルトゥーンスポーツ選手伝説", "UCjAvJkRe2mcTJWpKz3zZcEA"),
    ("corporate_fall", "corpfall-nokia",             "バルトゥーン倒産企業",         "UC7QIKudSkcsBaIy29_2A66A"),
    ("animals",        "animals-otter-handholding",  "バルトゥーン動物雑学",         "UCQJd-ETD71_akjpD4zcZSDA"),
    ("animals",        "animals-platypus",           "バルトゥーン動物雑学",         "UCQJd-ETD71_akjpD4zcZSDA"),
    ("astronomy",      "astro-saturn-rings-vanish",  "バルトゥーン宇宙",             "UCbUUphOk5EVhtfEi2POlfYQ"),
    ("astronomy",      "astro-betelgeuse-supernova", "バルトゥーン宇宙",             "UCbUUphOk5EVhtfEi2POlfYQ"),
]

GAP = 25  # seconds between uploads


def main() -> int:
    only = set(sys.argv[1:])
    rows = [r for r in ROWS if not only or r[1] in only]
    print(f"=== batch upload: {len(rows)} videos ===", flush=True)
    results = []
    for i, (proj, sid, disp, uc) in enumerate(rows, 1):
        print(f"\n[{i}/{len(rows)}] {proj}/{sid} -> {disp}", flush=True)
        p = subprocess.run([PYBIN, SCRIPT, proj, sid, disp, uc],
                           capture_output=True, text=True)
        out = (p.stdout or "") + (p.stderr or "")
        link = ""
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("published link:") or s.startswith("recorded in log:") \
               or "WRONG CHANNEL" in s or "confirmed: Publish anyway" in s or s == "DONE":
                print("   " + s[:160], flush=True)
            if s.startswith("published link:"):
                link = s.split("published link:", 1)[1].strip()
        ok = "DONE" in out and "WRONG CHANNEL" not in out
        results.append((proj, sid, "OK" if ok else "FAIL", link))
        if i < len(rows):
            time.sleep(GAP)

    print("\n===== SUMMARY =====", flush=True)
    for proj, sid, st, link in results:
        print(f"  [{st}] {proj}/{sid}  {link}", flush=True)
    n_ok = sum(1 for r in results if r[2] == "OK")
    print(f"\n{n_ok}/{len(results)} published", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
