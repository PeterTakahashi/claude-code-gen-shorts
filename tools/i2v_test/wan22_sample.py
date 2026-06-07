"""Smoke test: Wan 2.2 i2v via fal.ai.

Sends one local panel image + motion prompt to fal-ai/wan-25-preview/image-to-video
and downloads the resulting mp4 to /tmp/wan22_samples/.

Usage:
  uv run python tools/i2v_test/wan22_sample.py <panel.png> "<motion prompt>" [out.mp4]

The FAL_KEY env var must be set (or FAL_AI_API_KEY → mapped below).
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

# fal-client reads FAL_KEY; map from our .env name if needed.
if not os.environ.get("FAL_KEY") and os.environ.get("FAL_AI_API_KEY"):
    os.environ["FAL_KEY"] = os.environ["FAL_AI_API_KEY"]

import fal_client  # noqa: E402

# Endpoint slug for Wan 2.2 i2v on fal. The current public-A-tier endpoint is:
#   fal-ai/wan/v2.2-5b/image-to-video        (5B variant, cheapest)
#   fal-ai/wan/v2.2-a14b/image-to-video      (14B "MoE", higher quality, more expensive)
# We try the 14B variant by default (still very cheap relative to Kling/Runway).
ENDPOINT = os.environ.get("WAN_ENDPOINT", "fal-ai/wan/v2.2-a14b/image-to-video")


def upload_image(p: Path) -> str:
    """Upload a local image to fal's storage and return the public URL."""
    url = fal_client.upload_file(str(p))
    print(f"  uploaded {p.name} -> {url}")
    return url


def i2v(image_url: str, prompt: str, *, duration: int = 5, seed: int | None = None) -> dict:
    args = {
        "prompt": prompt,
        "image_url": image_url,
        "num_frames": 81,            # ~5s at 16fps (Wan 2.2 default)
        "resolution": "720p",
        "aspect_ratio": "9:16",      # vertical shorts
    }
    if seed is not None:
        args["seed"] = seed
    print(f"  submit -> {ENDPOINT}  prompt={prompt!r}")
    t0 = time.time()

    def on_update(update):
        if isinstance(update, fal_client.InProgress):
            for L in (update.logs or []):
                msg = L.get("message") if isinstance(L, dict) else getattr(L, "message", str(L))
                print(f"    log: {msg}")
        elif isinstance(update, fal_client.Queued):
            print(f"    queued (pos={update.position})")

    result = fal_client.subscribe(ENDPOINT, arguments=args, with_logs=True, on_queue_update=on_update)
    print(f"  done in {time.time()-t0:.1f}s")
    return result


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    panel = Path(sys.argv[1])
    prompt = sys.argv[2]
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp/wan22_samples") / (panel.stem + ".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    image_url = upload_image(panel)
    result = i2v(image_url, prompt)

    video_url = result.get("video", {}).get("url") if isinstance(result.get("video"), dict) else result.get("video_url")
    if not video_url:
        print(f"ERROR: no video url in result: {result}", file=sys.stderr)
        return 1
    print(f"  downloading {video_url}")
    urllib.request.urlretrieve(video_url, out)
    print(f"  wrote {out}  ({out.stat().st_size/1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
