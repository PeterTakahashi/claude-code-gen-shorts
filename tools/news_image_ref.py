#!/usr/bin/env python3
"""Fetch a reference image from a web image search for the given query.

Used by short_gen to ground panel generation against a real news photo
(then nanobanana redraws an original — copyright safe). We scrape Bing's
image-search results page because it doesn't require an API key and the
top-result URL is embedded in a predictable JSON-in-HTML field.

Standalone:
  .venv/bin/python tools/news_image_ref.py "孫正義 WeWork" --out /tmp/ref.jpg

As a library:
  from news_image_ref import fetch_reference_image
  path = fetch_reference_image("nvidia jensen huang", out_dir=Path("/tmp"))
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _bing_image_urls(query: str, top_n: int = 5) -> list[str]:
    """Scrape Bing image search; return the top-N image URLs."""
    url = (f"https://www.bing.com/images/search?q={quote_plus(query)}"
           "&form=HDRSC2&first=1")
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.9"},
                     timeout=20)
    if not r.ok:
        return []
    html = r.text
    # Each result tile carries a JSON blob in `m="...&quot;murl&quot;:&quot;<URL>&quot;..."`.
    # Pull the murl values (decoded HTML entities) in document order.
    urls: list[str] = []
    for m in re.finditer(r'murl&quot;:&quot;([^&]+)&quot;', html):
        u = m.group(1)
        # de-entitize and basic validation
        u = u.replace("&amp;", "&")
        if u.startswith("http") and u not in urls:
            urls.append(u)
        if len(urls) >= top_n:
            break
    return urls


def fetch_reference_image(query: str, *, out_dir: Path,
                          min_bytes: int = 8000,
                          max_bytes: int = 8 * 1024 * 1024) -> Path | None:
    """Search and download the first usable image for `query` into out_dir.

    Returns the local path, or None if all candidates fail. Cached by query
    hash so repeated calls reuse the file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        cached = out_dir / f"{key}{ext}"
        if cached.is_file() and cached.stat().st_size >= min_bytes:
            print(f"  ref(cache): {cached.name}  ({query!r})", flush=True)
            return cached

    urls = _bing_image_urls(query, top_n=6)
    if not urls:
        print(f"  ref: no results for {query!r}", flush=True)
        return None
    for i, u in enumerate(urls):
        try:
            r = requests.get(u, headers={"User-Agent": UA,
                                          "Referer": "https://www.bing.com/"},
                             timeout=15, stream=True)
            if not r.ok:
                continue
            content_type = (r.headers.get("Content-Type") or "").lower()
            if "image" not in content_type:
                continue
            # determine ext
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"
            else:
                ext = ".jpg"
            data = r.content
            if not (min_bytes <= len(data) <= max_bytes):
                continue
            out = out_dir / f"{key}{ext}"
            out.write_bytes(data)
            print(f"  ref({i+1}/{len(urls)}): {out.name} from {u[:60]}…  "
                  f"({len(data)/1024:.0f}KB)", flush=True)
            return out
        except Exception as e:
            print(f"  ref try {i+1} failed: {str(e)[:80]}", flush=True)
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output file path (default: /tmp/ref_<hash>.<ext>)")
    args = ap.parse_args()
    out_dir = args.out.parent if args.out else Path("/tmp")
    path = fetch_reference_image(args.query, out_dir=out_dir)
    if not path:
        print("FAIL: no image fetched", file=sys.stderr); return 2
    if args.out and args.out != path:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(path.read_bytes())
        path = args.out
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
