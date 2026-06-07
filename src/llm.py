"""Wrappers around external LLM CLIs and direct API calls.

`claude -p` is used for the LLM-authored stages of the in-project pipeline:
  - extract_characters: novel.txt → characters.yaml
  - decompose_scenes:   chapter novel.txt → scenes.json
  - author_bubbles:     scenes.json + rendered panel images → bubbles.json (vision)

Gemini is used by `src/plan_series.py` for series-level research and
multi-episode planning (Gemini's bigger context window + factual recall make
it a good fit for "research a real person, then plan 12 episodes").

Two Gemini transports are provided:
  - `run_gemini_p()`   — subprocesses the `gemini` CLI (works for users with the
                          subscription auth flow set up; uses GEMINI_API_KEY if
                          present)
  - `run_gemini_api()` — direct REST against the Google AI Studio endpoint with
                          `GEMINI_API_KEY`. Faster, no CLI overhead, and the call
                          is logged in the API console for transparent quota
                          tracking. Preferred when GEMINI_API_KEY is set.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .project import REPO_ROOT, ProjectContext


load_dotenv(override=True)


PROMPTS_DIR = REPO_ROOT / "prompts"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_RETRY_DELAY_RE = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


def _ensure_claude_on_path() -> None:
    if shutil.which("claude") is None:
        raise RuntimeError(
            "Claude Code CLI ('claude') not found on PATH. Install it from "
            "https://claude.com/claude-code or run the LLM step yourself and "
            "drop the output file into the expected path."
        )


def run_claude_p(
    prompt_template: str,
    *,
    context_files: list[Path],
    output_path: Path,
    extra_vars: dict[str, str] | None = None,
) -> Path:
    """Invoke `claude --dangerously-skip-permissions -p <prompt>`.

    The prompt template can contain {{var}} placeholders substituted from
    extra_vars. Context files are referenced as `@<absolute-path>` so Claude
    reads them via its own Read tool — keeps argv small.
    Returns the output path on success; raises if the file wasn't written.
    """
    _ensure_claude_on_path()

    body = prompt_template
    for k, v in (extra_vars or {}).items():
        body = body.replace(f"{{{{{k}}}}}", v)

    # Make path instructions explicit so Claude can't drift.
    body += "\n\n---\n"
    body += f"Write the result to: {output_path}\n"
    if context_files:
        body += "Read these files first:\n"
        for p in context_files:
            body += f"  @{p}\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    print(f"\n[llm] claude -p → {output_path}  (prompt: {len(body)} chars)")
    cmd = ["claude", "--dangerously-skip-permissions", "-p", body]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exited with status {proc.returncode}")

    if not output_path.exists():
        raise RuntimeError(
            f"claude -p completed but did not write {output_path}. "
            "Re-run this stage, or run the prompt yourself in an interactive "
            "Claude Code session and save the file by hand."
        )
    return output_path


def extract_characters(project: ProjectContext) -> Path:
    template = (PROMPTS_DIR / "extract_characters.md").read_text(encoding="utf-8")
    return run_claude_p(
        template,
        context_files=[project.input_novel, project.project_yaml],
        output_path=project.characters_yaml,
        extra_vars={
            "title": project.title_ja,
            "era": project.era,
            "language": project.language,
        },
    )


def decompose_scenes(project: ProjectContext, chapter_id: str) -> Path:
    template = (PROMPTS_DIR / "decompose_scenes.md").read_text(encoding="utf-8")
    chapter = project.chapter(chapter_id)
    return run_claude_p(
        template,
        context_files=[chapter.novel_txt, project.characters_yaml, project.project_yaml],
        output_path=chapter.scenes_json,
        extra_vars={
            "chapter_id": chapter_id,
            "chapter_title": chapter.title,
            "title": project.title_ja,
            "era": project.era,
        },
    )


def _list_chapter_panel_images(chapter) -> list[Path]:
    """All `<scene_id>/<panel_id>_best.png` under the chapter's panels dir, sorted."""
    if not chapter.panels_dir.exists():
        return []
    return sorted(chapter.panels_dir.glob("*/*_best.png"))


def _ensure_gemini_on_path() -> None:
    if shutil.which("gemini") is None:
        raise RuntimeError(
            "Gemini CLI ('gemini') not found on PATH. Install via "
            "https://github.com/google/gemini-cli or use the API directly."
        )


def run_gemini_p(
    prompt: str,
    *,
    model: str = "gemini-2.5-pro",
    timeout_s: float = 900.0,
) -> str:
    """Invoke `gemini -p <prompt>` in headless mode. Returns stdout.

    `--yolo` auto-approves any tool calls Gemini might want to make so the
    process doesn't hang waiting for confirmation in non-interactive mode.
    `GEMINI_API_KEY` from .env is inherited via load_dotenv at module import.
    """
    _ensure_gemini_on_path()
    cmd = ["gemini", "-p", prompt, "-m", model, "--yolo"]
    print(f"  → gemini -m {model}  ({len(prompt)} chars prompt)")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError(
            f"gemini -p exited with status {proc.returncode}.\n"
            f"stderr: {proc.stderr[:1500]}"
        )
    return proc.stdout


def _gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set (check .env or shell env)")
    return key


def run_gemini_api(
    prompt: str,
    *,
    model: str = "gemini-2.5-pro",
    timeout_s: float = 600.0,
    max_attempts: int = 6,
    response_mime_type: str | None = None,
) -> str:
    """Call Gemini generateContent via direct REST. Returns the text response.

    Handles 429 / RESOURCE_EXHAUSTED with exponential-with-jitter backoff (the
    Gemini error body includes a retryDelay hint we honor when present).
    Optionally pass `response_mime_type="application/json"` to force JSON output.
    """
    api_key = _gemini_api_key()
    body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
    if response_mime_type:
        body["generationConfig"] = {"responseMimeType": response_mime_type}
    url = f"{GEMINI_API_BASE}/{model}:generateContent"
    headers = {"Content-Type": "application/json", "X-goog-api-key": api_key}

    print(f"  → gemini-api {model}  ({len(prompt)} chars prompt)")
    with httpx.Client(timeout=timeout_s) as client:
        for attempt in range(1, max_attempts + 1):
            r = client.post(url, json=body, headers=headers)
            if r.status_code == 200:
                break
            if r.status_code in (429, 503) and attempt < max_attempts:
                m = _GEMINI_RETRY_DELAY_RE.search(r.text)
                wait = float(m.group(1)) + 1.0 if m else min(60.0, 5.0 * attempt)
                print(
                    f"    {r.status_code} retryable; waiting {wait:.1f}s "
                    f"(attempt {attempt}/{max_attempts})"
                )
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"gemini-api {model}: HTTP {r.status_code}\n{r.text[:1500]}"
            )
        else:
            raise RuntimeError(
                f"gemini-api {model}: exhausted {max_attempts} retries with 429/503"
            )

    data = r.json()
    parts = []
    for c in data.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            t = p.get("text")
            if t:
                parts.append(t)
    if not parts:
        raise RuntimeError(f"gemini-api {model}: empty response: {data!r}")
    return "".join(parts)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull a JSON object/array out of an LLM response.

    Handles ```json ... ``` fences and bare JSON with preamble/postamble.
    Picks the matching outer pair based on which bracket character appears
    first in the stripped text — i.e. if the document starts with `{` we
    look for the matching `}`, never confusing it with an inner `[ ... ]`
    array that happens to come earlier in the byte stream.
    Returns the JSON string only (not parsed) so the caller can json.loads
    it and surface decode errors with full context.
    """
    text = text.strip()
    m = _JSON_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    first_obj = text.find("{")
    first_arr = text.find("[")
    if first_obj == -1 and first_arr == -1:
        return text
    if first_arr == -1 or (first_obj != -1 and first_obj < first_arr):
        first, last_char = first_obj, "}"
    else:
        first, last_char = first_arr, "]"
    last = text.rfind(last_char)
    if 0 <= first < last:
        return text[first : last + 1]
    return text


def author_bubbles(project: ProjectContext, chapter_id: str) -> Path:
    """Vision-aware bubble authoring.

    Claude is given the chapter's scenes.json + novel.txt + every rendered
    panel image (via @path references). It writes bubbles.json with positions
    chosen against the actual artwork.

    Pre-condition: scenes.json exists AND every non-reuse panel has been rendered.
    Pipeline ensures this by running render_panels before author_bubbles.
    """
    template = (PROMPTS_DIR / "author_bubbles.md").read_text(encoding="utf-8")
    chapter = project.chapter(chapter_id)

    panel_images = _list_chapter_panel_images(chapter)
    if not panel_images:
        raise RuntimeError(
            f"no rendered panel images under {chapter.panels_dir}. "
            "Run render_panels (S11) before author_bubbles (S9)."
        )

    context_files = [
        chapter.scenes_json,
        chapter.novel_txt,
        project.characters_yaml,
        project.project_yaml,
        *panel_images,
    ]
    return run_claude_p(
        template,
        context_files=context_files,
        output_path=chapter.bubbles_json,
        extra_vars={
            "chapter_id": chapter_id,
            "chapter_title": chapter.title,
            "title": project.title_ja,
        },
    )
