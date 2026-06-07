"""OpenAI gpt-image-1 client — vertical (9:16-ish) image generation.

Pricing (2025/04 update):
  - low quality 1024x1024:   ~$0.011 per image
  - medium quality:           ~$0.042 per image
  - high quality:             ~$0.167 per image
  - 1024x1536 (portrait):     slightly higher than square equivalent

For shorts panels: 'medium' quality at 1024x1536 ≈ $0.05/img — vs Gemini batch
nanobanana ~$0.02/img. So OpenAI is 2.5x more at medium, but cheaper at 'low'.

We default to **medium** for quality, **1024x1536** for the closest available
vertical aspect ratio. short_gen.py's _fit_native_vertical() resizes to
1080x1920 (9:16) after.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from openai import OpenAI

DEFAULT_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
# 1024x1024 = ~33% cheaper than 1024x1536. We center-place the square in the
# vertical canvas with blurred top/bottom (handled by short_gen).
DEFAULT_SIZE = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024")
DEFAULT_QUALITY = os.environ.get("OPENAI_IMAGE_QUALITY", "medium")  # low | medium | high


def generate_image_openai(prompt: str, out_path: Path, *,
                          model: str = DEFAULT_MODEL,
                          size: str = DEFAULT_SIZE,
                          quality: str = DEFAULT_QUALITY,
                          background: str = "auto") -> Path:
    """Generate one image via OpenAI Images API. Saves PNG to out_path."""
    client = OpenAI()
    resp = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
        # gpt-image-1 returns b64_json by default
    )
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        png_bytes = base64.b64decode(item.b64_json)
    elif getattr(item, "url", None):
        # fall-through: download
        import httpx
        png_bytes = httpx.get(item.url, timeout=60.0).content
    else:
        raise RuntimeError(f"no b64_json or url in OpenAI response: {item}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(png_bytes)
    return out_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--size", default=DEFAULT_SIZE)
    p.add_argument("--quality", default=DEFAULT_QUALITY)
    args = p.parse_args()

    out = generate_image_openai(args.prompt, args.out, size=args.size, quality=args.quality)
    print(f"wrote {out}  ({out.stat().st_size} bytes)")
