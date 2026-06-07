#!/usr/bin/env python3
"""Drain the upload backlog, pacing around YouTube's *daily* video-upload cap.

The 429 we keep hitting is `Video Uploads per day` (a DAILY limit, reason
rateLimitExceeded). Short sleeps don't help — once the day's allotment is used,
every further upload 429s until the daily reset (midnight US Pacific ≈ 16:00 JST).

So: upload until a 429 is seen, then sleep until just after the next reset and
resume. Already-uploaded shorts are skipped by youtube_batch_upload_shorts
(it only skips entries that already have a video_id), so re-running is safe.

Runs as a long-lived background process (may span 2-3 days for a ~20 backlog at
~10 uploads/day). Keep the Mac awake. Ctrl-C to stop; rerun to resume.
"""
import datetime
import subprocess
import sys
import time
import zoneinfo

JST = zoneinfo.ZoneInfo("Asia/Tokyo")
ROOT = "/Users/apple/dev/claude-code/webtoon-gen"
PY = f"{ROOT}/.venv/bin/python"

# (project, channel, comma-separated short_ids). housing_regret/money_failure
# omitted (no channel yet). Already-uploaded ones are skipped automatically.
# CLEAN nanobanana shorts only (text-free / accurate likeness). The FLUX backlog
# was removed 2026-05-25: those panels still garble in-image Japanese on
# scene/signage/infographic compositions and must be rewritten (photorealistic,
# text-free) + regenerated before they're safe to publish.
ROWS = [
    # Top-6-channel batch (2026-05-25): 12 clean shorts (nanobanana likeness/scene +
    # FLUX photorealistic text-free). Already-uploaded ones are skipped automatically.
    ("tadashiyanai", "ijinden_ja", "yanai-uk-failure"),
    ("elonmusk", "ijinden_ja", "musk-2008-broke"),
    ("japan_praise", "baltoon_japan_praise_ja", "jp-department-bow,jp-vending-machine"),
    ("sports_legends", "baltoon_sports_legends_ja", "sports-hanyu-2peat,sports-oh-868"),
    ("corporate_fall", "baltoon_corporate_fall_ja", "corpfall-kodak,corpfall-nokia"),
    ("animals", "baltoon_animals_ja", "animals-otter-handholding,animals-platypus"),
    ("astronomy", "baltoon_astronomy_ja", "astro-saturn-rings-vanish,astro-betelgeuse-supernova"),
]

INTER_UPLOAD_SLEEP = 8       # gentle gap between uploads (avoids burst flags)
RESET_HOUR_JST = 16          # PT-midnight ≈ 16:00 JST; resume a bit after
RESET_RESUME_MIN = 20        # resume at 16:20 JST to be safely past the reset


def secs_until_next_reset() -> float:
    now = datetime.datetime.now(JST)
    reset = now.replace(hour=RESET_HOUR_JST, minute=RESET_RESUME_MIN, second=0, microsecond=0)
    if now >= reset:
        reset += datetime.timedelta(days=1)
    return (reset - now).total_seconds()


def run_one(project: str, channel: str, only: str) -> tuple[int, bool]:
    """Run the batch uploader for one project. Returns (num_uploaded, quota_hit)."""
    cmd = [PY, "-m", "src.youtube_batch_upload_shorts", project,
           "--channel", channel, "--only", only, "--privacy", "public"]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    uploaded = out.count("uploaded — video_id")
    quota = "Quota exceeded" in out or "rateLimitExceeded" in out
    for line in out.splitlines():
        if any(k in line for k in ("uploaded — video_id", "already uploaded", "Quota exceeded", "no title")):
            print("    " + line.strip()[:140], flush=True)
    return uploaded, quota


def main() -> int:
    total = 0
    cycle = 0
    while True:
        cycle += 1
        print(f"\n===== cycle {cycle}  {datetime.datetime.now(JST):%Y-%m-%d %H:%M JST} =====", flush=True)
        progressed = False
        quota_hit = False
        for project, channel, only in ROWS:
            print(f">>> {project} -> {channel}", flush=True)
            up, quota = run_one(project, channel, only)
            total += up
            if up:
                progressed = True
            time.sleep(INTER_UPLOAD_SLEEP)
            if quota:
                quota_hit = True
                print("  >>> daily quota hit — will sleep until reset", flush=True)
                break
        if not quota_hit and not progressed:
            print(f"\n✅ backlog drained — {total} uploaded across {cycle} cycle(s)", flush=True)
            return 0
        if quota_hit:
            s = secs_until_next_reset()
            wake = datetime.datetime.now(JST) + datetime.timedelta(seconds=s)
            print(f"  sleeping {s / 3600:.1f}h until ~{wake:%m-%d %H:%M JST} (next quota reset)…", flush=True)
            time.sleep(s + 60)


if __name__ == "__main__":
    raise SystemExit(main())
