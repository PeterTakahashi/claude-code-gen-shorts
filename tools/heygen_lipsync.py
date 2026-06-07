#!/usr/bin/env python3
"""HeyGen v3 lipsync — given an avatar_id (pre-created in HeyGen) + audio mp3,
generate a talking-head mp4 via HeyGen's Create Video API.

API flow:
  1. POST /v3/assets (multipart) — upload audio, get asset_id
  2. POST /v3/videos {type:avatar, avatar_id, audio_asset_id, resolution,
                      aspect_ratio} — submit job, get video_id
  3. GET /v3/videos/{video_id} — poll until status==completed → video_url
  4. download video_url → out_path

Reads HEYGEN_API_KEY from .env. The default avatar_id matches the user's
configured news anchor.

Standalone:
  .venv/bin/python tools/heygen_lipsync.py \\
    --avatar-id 0f1f2b6e994740f98b195ca8320567f3 \\
    --audio /tmp/opener.mp3 \\
    --out /tmp/opener_heygen.mp4
"""
import argparse
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path("/Users/apple/dev/claude-code/webtoon-gen")
env = dotenv_values(ROOT / ".env")
API_KEY = env.get("HEYGEN_API_KEY")
DEFAULT_AVATAR_ID = "d996f26d99e84e9f801d87dc5290b36a"  # Newsroom Anchor look (group 0f1f2b6e…)
BASE = "https://api.heygen.com/v3"


def _hdr(extra: dict | None = None) -> dict:
    h = {"x-api-key": API_KEY}
    if extra:
        h.update(extra)
    return h


def upload_audio(path: Path) -> str:
    """POST /v3/assets multipart. Returns asset_id."""
    path = Path(path)
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "audio/mpeg")}
        r = requests.post(f"{BASE}/assets", headers=_hdr(), files=files, timeout=120)
    if not r.ok:
        raise RuntimeError(f"upload_asset failed: {r.status_code} {r.text[:400]}")
    data = r.json().get("data", {})
    asset_id = data.get("asset_id")
    if not asset_id:
        raise RuntimeError(f"no asset_id in upload response: {r.json()}")
    print(f"    asset_id: {asset_id} ({data.get('size_bytes')} bytes)", flush=True)
    return asset_id


def create_video(avatar_id: str, audio_asset_id: str, *,
                 aspect_ratio: str = "9:16", resolution: str = "1080p") -> str:
    """POST /v3/videos. Returns video_id."""
    body = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "audio_asset_id": audio_asset_id,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
    }
    r = requests.post(f"{BASE}/videos",
                      headers=_hdr({"Content-Type": "application/json"}),
                      json=body, timeout=60)
    if not r.ok:
        raise RuntimeError(f"create_video failed: {r.status_code} {r.text[:400]}")
    data = r.json().get("data", {})
    video_id = data.get("video_id") or data.get("id")
    if not video_id:
        raise RuntimeError(f"no video_id in response: {r.json()}")
    print(f"    video_id: {video_id}", flush=True)
    return video_id


def poll_video(video_id: str, poll_secs: float = 5.0,
               timeout_secs: float = 600.0) -> str:
    """Poll GET /v3/videos/{id} until status==completed; return video_url."""
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        r = requests.get(f"{BASE}/videos/{video_id}", headers=_hdr(), timeout=30)
        if not r.ok:
            print(f"    poll {r.status_code}: {r.text[:200]}", flush=True)
            time.sleep(poll_secs); continue
        d = r.json().get("data", {})
        status = (d.get("status") or "").lower()
        print(f"    status: {status}", flush=True)
        if status == "completed":
            url = d.get("video_url")
            if not url:
                raise RuntimeError(f"completed but no video_url: {d}")
            return url
        if status in ("failed", "error", "rejected"):
            raise RuntimeError(
                f"heygen job {status}: code={d.get('failure_code')} "
                f"msg={d.get('failure_message')}"
            )
        time.sleep(poll_secs)
    raise TimeoutError(f"timed out polling video {video_id}")


def lipsync(avatar_id: str, audio_path: Path, out_path: Path,
            *, aspect_ratio: str = "9:16", resolution: str = "1080p") -> Path:
    if not API_KEY:
        raise RuntimeError("HEYGEN_API_KEY missing in .env")
    audio_path = Path(audio_path); out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  uploading audio: {audio_path.name}", flush=True)
    asset_id = upload_audio(audio_path)
    print(f"  submitting HeyGen video (avatar={avatar_id[:8]}…)", flush=True)
    video_id = create_video(avatar_id, asset_id,
                            aspect_ratio=aspect_ratio, resolution=resolution)
    url = poll_video(video_id)
    print(f"  downloading {url[:80]}…", flush=True)
    rd = requests.get(url, timeout=180)
    rd.raise_for_status()
    out_path.write_bytes(rd.content)
    print(f"  ✓ saved {out_path}  ({out_path.stat().st_size/1024/1024:.1f} MB)",
          flush=True)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--avatar-id", default=DEFAULT_AVATAR_ID)
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--aspect-ratio", default="9:16",
                    choices=["16:9", "9:16", "4:5", "5:4", "1:1", "auto"])
    ap.add_argument("--resolution", default="1080p",
                    choices=["720p", "1080p", "4k"])
    args = ap.parse_args()
    lipsync(args.avatar_id, args.audio, args.out,
            aspect_ratio=args.aspect_ratio, resolution=args.resolution)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
