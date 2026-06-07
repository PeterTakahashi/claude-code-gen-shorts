"""Call Gemini 2.5 Flash Image (nanobanana) via raw v1beta REST.

We use the raw REST endpoint (not the google-genai SDK) because the SDK
re-routes `gemini-2.5-flash-image` to the preview variant whose free-tier
quota is 0, while the GA model endpoint works directly via curl-equivalent
HTTPS POST.

This module exposes two entry points:

- `generate_image(...)` — synchronous single-image generation (the v1 path).
- `generate_images_batch(...)` — Batch API generation at 50% cost. Submits
  all (prompt, out_path, refs) tuples as one inline batch, polls until
  done, and writes successful images. Batch API has up to a 24h SLA so
  this is intended for finalized production runs, not interactive iteration.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import subprocess
import tempfile
import time
import zlib
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .config import GEMINI_MODEL


_RETRY_DELAY_RE = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


load_dotenv(override=True)

# ---- Local FLUX.2 (MLX) backend ----------------------------------------------
# Set IMAGE_BACKEND=flux2-local to generate panels locally on Apple Silicon via
# mflux (separate arm64 venv), instead of the Gemini "nanobanana" API. Free, no
# credits, ~26s/image (4-step Klein). Tunable via env vars below.
_FLUX2_BIN = os.path.expanduser(os.environ.get(
    "FLUX2_BIN", "~/flux2-mlx/bin/mflux-generate-flux2"))
_FLUX2_MODEL = os.environ.get("FLUX2_MODEL", "flux2-klein-4b")
_FLUX2_STEPS = os.environ.get("FLUX2_STEPS", "4")
_FLUX2_QUANT = os.environ.get("FLUX2_QUANT", "4")
_FLUX2_SIZE = os.environ.get("FLUX2_SIZE", "1024")  # square, matches panel pipeline

# FLUX.2 Klein (distilled, no CFG so negative prompts don't work) ignores the
# prefix "No text" hint and paints garbled pseudo-Japanese. A strong, explicit
# in-prompt directive reliably suppresses it. Readable captions are burned in by
# the short pipeline (PIL), so panels never need in-image text.
_FLUX2_NOTEXT = (
    " CRITICAL: This image must contain absolutely NO text of any kind — "
    "no letters, no Japanese or Chinese characters, no words, no numbers, no captions, "
    "no labels, no signs, no watermarks, no writing anywhere. A purely visual illustration with zero text."
)


def _flux2_prompt(prompt: str) -> str:
    """Append the strong no-text directive for FLUX (idempotent)."""
    return prompt if _FLUX2_NOTEXT in prompt else (prompt + _FLUX2_NOTEXT)


def _flux2_enabled() -> bool:
    return os.environ.get("IMAGE_BACKEND", "").lower() == "flux2-local"


def _generate_flux2_local(prompt: str, out_path: Path) -> Path:
    """Generate one panel locally with FLUX.2 Klein via mflux (subprocess).

    mflux lives in its own arm64 venv (the project venv may be x86_64 and cannot
    import mlx), so we shell out. Seed is derived from the output name so re-runs
    are deterministic per panel.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seed = str(zlib.crc32(out_path.stem.encode("utf-8")) % 2_000_000_000)
    cmd = [
        _FLUX2_BIN, "--model", _FLUX2_MODEL,
        "--steps", _FLUX2_STEPS, "--quantize", _FLUX2_QUANT,
        "--width", _FLUX2_SIZE, "--height", _FLUX2_SIZE,
        "--seed", seed, "--output", str(out_path), "--prompt", _flux2_prompt(prompt),
    ]
    env = {**os.environ, "HF_HUB_ENABLE_HF_TRANSFER": "1"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900)
    if not out_path.exists():
        raise RuntimeError(
            f"flux2-local generation failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[-500:]}")
    return out_path


def generate_images_flux2_batch(jobs, *, poll_interval_s: float = 30.0, display_name=None):
    """Generate all panels with ONE local FLUX.2 model load (the fast path).

    Mirrors generate_images_batch's signature/return so short_gen's batch path
    can route here when IMAGE_BACKEND=flux2-local. jobs: list of
    (prompt, out_path, refs); refs ignored. Returns (written_paths, failures).
    """
    if not jobs:
        return [], []
    flux_py = os.path.expanduser("~/flux2-mlx/bin/python")
    helper = str(Path(__file__).resolve().parent.parent / "tools" / "flux2_batchgen.py")
    spec = []
    for (prompt, out_path, _refs) in jobs:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        seed = zlib.crc32(Path(out_path).stem.encode("utf-8")) % 2_000_000_000
        spec.append({"prompt": _flux2_prompt(prompt), "output": str(out_path), "seed": seed})
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(spec, tf)
        jobs_json = tf.name
    cmd = [flux_py, helper, jobs_json, _FLUX2_MODEL, _FLUX2_QUANT, _FLUX2_STEPS, _FLUX2_SIZE]
    env = {**os.environ, "HF_HUB_ENABLE_HF_TRANSFER": "1"}
    print(f"  → FLUX.2 local batch: {len(jobs)} image(s), single model load…")
    subprocess.run(cmd, env=env)  # progress streams to stdout
    written, failures = [], []
    for i, (_p, out_path, _r) in enumerate(jobs):
        if Path(out_path).exists():
            written.append(out_path)
        else:
            failures.append((i, "flux2 batch produced no output"))
    return written, failures

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set (check .env)")
    return key


def _image_part(path: Path) -> dict:
    mime, _ = mimetypes.guess_type(path.name)
    return {
        "inlineData": {
            "mimeType": mime or "image/png",
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
    }


def generate_image(
    prompt: str,
    out_path: Path,
    reference_images: list[Path] | None = None,
    model: str = GEMINI_MODEL,
    timeout_s: float = 120.0,
) -> Path:
    """Generate one image from prompt (+ optional refs) and save PNG to out_path."""
    if _flux2_enabled():
        return _generate_flux2_local(prompt, out_path)
    parts: list[dict] = [{"text": prompt}]
    for ref in reference_images or []:
        parts.append(_image_part(ref))

    body = {"contents": [{"parts": parts}]}
    url = f"{API_BASE}/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": _api_key(),
    }

    empty_retry_max = 3
    with httpx.Client(timeout=timeout_s) as client:
        max_attempts = 6
        for empty_attempt in range(1, empty_retry_max + 1):
            for attempt in range(1, max_attempts + 1):
                r = client.post(url, json=body, headers=headers)
                if r.status_code == 200:
                    break
                if r.status_code == 429 and attempt < max_attempts:
                    m = _RETRY_DELAY_RE.search(r.text)
                    wait = float(m.group(1)) + 1.0 if m else min(60.0, 5.0 * attempt)
                    print(f"  429 rate-limited, waiting {wait:.1f}s (attempt {attempt}/{max_attempts})")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"{r.status_code} {r.text[:500]}")
            else:
                raise RuntimeError(f"gave up after {max_attempts} 429s")
            data = r.json()

            for c in data.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    inline = p.get("inlineData") or p.get("inline_data")
                    if inline and inline.get("data"):
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(base64.b64decode(inline["data"]))
                        return out_path

            # Empty/text-only response — retry a couple times before giving up.
            texts = [
                p.get("text", "")
                for c in data.get("candidates", [])
                for p in c.get("content", {}).get("parts", [])
                if p.get("text")
            ]
            if empty_attempt < empty_retry_max:
                print(f"  empty response, retrying ({empty_attempt}/{empty_retry_max}). texts={texts[:1]}")
                time.sleep(5)
                continue
            raise RuntimeError(f"No image returned after {empty_retry_max} tries. Text parts: {texts}")

    raise RuntimeError("unreachable")


def _write_image_part(parts: list[dict], out_path: Path) -> bool:
    """Walk `parts` and write the first inlineData PNG to out_path. Returns True if written."""
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(base64.b64decode(inline["data"]))
            return True
    return False


def generate_images_batch(
    jobs: list[tuple[str, Path, list[Path] | None]],
    *,
    model: str = GEMINI_MODEL,
    poll_interval_s: float = 30.0,
    max_wait_s: float = 86400.0,
    display_name: str | None = None,
) -> tuple[list[Path], list[tuple[int, str]]]:
    """Submit all (prompt, out_path, refs) jobs as one inline batch.

    Returns (written_out_paths, failures). `failures` is a list of (index, message)
    for jobs that errored or returned no image. Polls every `poll_interval_s`
    until the batch reaches a terminal state or `max_wait_s` elapses.
    """
    if not jobs:
        return [], []

    inlined: list[dict] = []
    for i, (prompt, _out, refs) in enumerate(jobs):
        parts: list[dict] = [{"text": prompt}]
        for ref in refs or []:
            parts.append(_image_part(ref))
        inlined.append({
            "request": {"contents": [{"parts": parts}]},
            "metadata": {"key": f"req_{i:03d}"},
        })

    body = {
        "batch": {
            "display_name": display_name or f"webtoon-gen-{int(time.time())}",
            "input_config": {
                "requests": {"requests": inlined},
            },
        }
    }
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": _api_key(),
    }
    submit_url = f"{API_BASE}/{model}:batchGenerateContent"

    with httpx.Client(timeout=300.0) as client:
        print(f"  → submitting batch ({len(jobs)} requests) to {model}…")
        r = client.post(submit_url, json=body, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"batch submit failed {r.status_code}: {r.text[:1000]}")
        op = r.json()
        batch_name = op.get("name")
        if not batch_name:
            raise RuntimeError(f"batch submit: no name in response: {op}")
        print(f"  batch submitted: {batch_name}")

        poll_url = f"{API_ROOT}/{batch_name}"
        deadline = time.time() + max_wait_s
        last_state: str | None = None
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"batch did not finish within {max_wait_s:.0f}s: {batch_name}")
            time.sleep(poll_interval_s)
            r = client.get(poll_url, headers=headers)
            if r.status_code != 200:
                print(f"  poll {r.status_code}: {r.text[:300]} — retrying")
                continue
            status = r.json()
            md = status.get("metadata") or {}
            state = md.get("state") or status.get("state")
            done = status.get("done", False)
            if state != last_state:
                print(f"  batch state: {state}{' (done)' if done else ''}")
                last_state = state
            if state in {"JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"} or done:
                break
            if state in {"JOB_STATE_FAILED", "BATCH_STATE_FAILED", "JOB_STATE_CANCELLED", "BATCH_STATE_CANCELLED"}:
                raise RuntimeError(f"batch ended in {state}: {status}")

    # Locate inlinedResponses. Observed shape (v1beta, Nov 2026):
    #   response.inlinedResponses = { "inlinedResponses": [ {response|error}, ... ] }
    # (i.e. the outer key wraps a single-field object whose value is the array)
    response = status.get("response") or {}
    raw = (
        response.get("inlinedResponses")
        or response.get("dest", {}).get("inlinedResponses")
        or md.get("dest", {}).get("inlinedResponses")
    )
    if isinstance(raw, dict):
        # Unwrap the {"inlinedResponses": [...]} envelope or any single-list value.
        inlined_responses = raw.get("inlinedResponses") or next(
            (v for v in raw.values() if isinstance(v, list)),
            [],
        )
    elif isinstance(raw, list):
        inlined_responses = raw
    else:
        inlined_responses = []

    if not inlined_responses:
        file_uri = (
            (response.get("dest") or {}).get("file")
            or (md.get("dest") or {}).get("file")
        )
        if file_uri:
            raise NotImplementedError(
                "batch returned file-based output; inline-only path implemented. "
                f"File URI: {file_uri}"
            )
        raise RuntimeError(f"batch succeeded but no inlinedResponses found: {status}")

    written: list[Path] = []
    failures: list[tuple[int, str]] = []
    for i, item in enumerate(inlined_responses):
        _, out_path, _ = jobs[i]
        err = item.get("error")
        if err:
            failures.append((i, f"{err}"))
            continue
        resp = item.get("response") or {}
        parts: list[dict] = []
        for c in resp.get("candidates", []):
            parts.extend(c.get("content", {}).get("parts", []))
        if _write_image_part(parts, out_path):
            written.append(out_path)
        else:
            texts = [p.get("text", "") for p in parts if p.get("text")]
            failures.append((i, f"no image returned; text parts: {texts[:1]}"))

    return written, failures
