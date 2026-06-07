#!/usr/bin/env python3
"""Sync.so v2 lipsync — combine a still image + an audio file into a talking-
head mp4. Used to produce a 5-7 sec "anchor opener" that gets prepended to a
generated news short.

The Sync.so API consumes public URLs. We upload the input files to 0x0.st
(ephemeral file host) and pass those URLs through. SYNC_AI_API_KEY in .env.

Standalone:
  .venv/bin/python tools/sync_lipsync.py \\
    --image assets/anchor.png --audio /tmp/opener.mp3 \\
    --out /tmp/opener_lipsync.mp4
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path("/Users/apple/dev/claude-code/webtoon-gen")
env = dotenv_values(ROOT / ".env")
API_KEY = env.get("SYNC_AI_API_KEY") or env.get("SYNCSO_API_KEY")
SYNC_BASE = "https://api.sync.so/v2"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def upload_public(path: Path) -> str:
    """Upload to a free ephemeral host, return the public URL."""
    path = Path(path)
    # tmpfiles.org first (more reliable than 0x0.st for automated uploads)
    try:
        r = requests.post("https://tmpfiles.org/api/v1/upload",
                          files={"file": (path.name, open(path, "rb"))},
                          headers={"User-Agent": UA}, timeout=60)
        if r.ok:
            data = r.json()
            # response: {"status":"success","data":{"url":"https://tmpfiles.org/<id>/<name>"}}
            url = data.get("data", {}).get("url", "")
            if url:
                # tmpfiles wraps the URL — the direct download is /dl/<id>/<name>
                return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception as e:
        print(f"  tmpfiles upload failed: {str(e)[:120]}", file=sys.stderr)
    # 0x0.st fallback
    try:
        r = requests.post("https://0x0.st",
                          files={"file": (path.name, open(path, "rb"))},
                          data={"expires": "24"},  # hours
                          headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        return r.text.strip()
    except Exception as e:
        raise RuntimeError(f"all upload hosts failed; last: {str(e)[:160]}")


def lipsync(image_path: Path, audio_path: Path, out_path: Path,
            model: str = "react-1", poll_secs: float = 4.0,
            timeout_secs: float = 600.0,
            options: dict | None = None) -> Path:
    if not API_KEY:
        raise RuntimeError("SYNC_AI_API_KEY missing in .env")
    image_path = Path(image_path); audio_path = Path(audio_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  uploading image: {image_path.name}", flush=True)
    image_url = upload_public(image_path)
    print(f"    -> {image_url}", flush=True)
    print(f"  uploading audio: {audio_path.name}", flush=True)
    audio_url = upload_public(audio_path)
    print(f"    -> {audio_url}", flush=True)

    # react-1 supports model_mode=head for natural talking-head head/face
    # motion even when the input video is mostly static. lipsync-2 needs
    # pre-existing mouth motion in the input.
    default_options: dict = {"output_format": "mp4"}
    if model.startswith("react"):
        default_options["model_mode"] = "head"
    if options:
        default_options.update(options)
    body = {
        "model": model,
        "input": [
            {"type": "video", "url": image_url},
            {"type": "audio", "url": audio_url},
        ],
        "options": default_options,
    }
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
    print(f"  submitting to Sync.so ({model})…", flush=True)
    r = requests.post(f"{SYNC_BASE}/generate", json=body, headers=headers, timeout=60)
    if not r.ok:
        raise RuntimeError(f"sync.so submit failed: {r.status_code} {r.text[:400]}")
    job = r.json()
    job_id = job.get("id")
    if not job_id:
        raise RuntimeError(f"no job id in response: {job}")
    print(f"    job_id: {job_id}", flush=True)

    deadline = time.time() + timeout_secs
    output_url = None
    while time.time() < deadline:
        time.sleep(poll_secs)
        rr = requests.get(f"{SYNC_BASE}/generate/{job_id}", headers=headers, timeout=30)
        if not rr.ok:
            print(f"    poll {rr.status_code}: {rr.text[:200]}", flush=True)
            continue
        s = rr.json()
        status = (s.get("status") or "").upper()
        print(f"    status: {status}", flush=True)
        if status in ("COMPLETED", "SUCCEEDED", "DONE"):
            # response shape varies between API revs — try multiple paths
            output_url = (s.get("outputUrl")
                          or s.get("output_url")
                          or (s.get("output") or {}).get("url")
                          or (s.get("output") or {}).get("video", {}).get("url"))
            if output_url:
                break
            raise RuntimeError(f"no output url in completed response: {s}")
        if status in ("FAILED", "ERROR", "CANCELLED", "REJECTED"):
            raise RuntimeError(f"sync.so job {status}: {s.get('error') or s}")
    if not output_url:
        raise TimeoutError(f"timed out waiting for sync.so job {job_id}")

    print(f"  downloading {output_url}", flush=True)
    rd = requests.get(output_url, timeout=120)
    rd.raise_for_status()
    out_path.write_bytes(rd.content)
    print(f"  ✓ saved {out_path}  ({out_path.stat().st_size/1024/1024:.1f} MB)",
          flush=True)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default="lipsync-2")
    args = ap.parse_args()
    lipsync(args.image, args.audio, args.out, model=args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
