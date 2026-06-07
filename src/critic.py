"""VLM critic for generated panel images (M7).

Scores each rendered panel via `claude -p` with the rubric in
`prompts/critic_panel.md`. Returns a structured JSON verdict per panel.

Used by render_panels for auto-retry when a panel scores below threshold or
flags fatal_flaw. Configurable via project.yaml `critic.*`.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .project import Chapter, ProjectContext, REPO_ROOT, load


PROMPTS_DIR = REPO_ROOT / "prompts"

# Defaults — overridable via project.yaml `critic.*`.
DEFAULT_THRESHOLD_TOTAL = 56   # max 80; below this we retry
DEFAULT_MAX_ROUNDS = 3


@dataclass
class CritiqueResult:
    panel_id: str
    scores: dict[str, int] = field(default_factory=dict)
    total: int = 0
    fatal_flaw: bool = False
    notes: str = ""
    retry_hints: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def passed(self) -> bool:
        return (not self.fatal_flaw) and (self.total >= DEFAULT_THRESHOLD_TOTAL)


def _ensure_claude() -> None:
    if shutil.which("claude") is None:
        raise RuntimeError("Claude Code CLI ('claude') not on PATH")


def _extract_json(text: str) -> dict | None:
    """Find the first balanced JSON object in `text`."""
    # Try direct parse first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Look for a fenced block.
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Find the first {...} block.
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = -1
                    continue
    return None


def critique_panel(
    project: ProjectContext,
    chapter: Chapter,
    panel: dict,
    panel_image: Path,
) -> CritiqueResult:
    """Run claude -p with the critic prompt, return parsed result."""
    _ensure_claude()
    template = (PROMPTS_DIR / "critic_panel.md").read_text(encoding="utf-8")

    # Stylesheet refs for character identity check.
    refs: list[Path] = []
    for c in panel.get("characters_in_panel", []):
        char = project.character(c["id"])
        if char is None:
            continue
        for p in (
            char.stylesheet_turnaround(project.project_dir),
            char.stylesheet_expression(project.project_dir),
        ):
            if p.exists():
                refs.append(p)

    body = template
    body = body.replace("{{panel_id}}", panel["panel_id"])
    body = body.replace("{{panel_json}}", json.dumps(panel, ensure_ascii=False))

    body += "\n\n---\nPanel image to critique: @" + str(panel_image)
    if refs:
        body += "\nCharacter stylesheets:\n" + "\n".join(f"  @{p}" for p in refs)
    body += "\n\nRespond with the JSON object only."

    cmd = ["claude", "--dangerously-skip-permissions", "-p", body]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    raw = (proc.stdout or "").strip()

    parsed = _extract_json(raw) or {}
    return CritiqueResult(
        panel_id=panel["panel_id"],
        scores=parsed.get("scores") or {},
        total=int(parsed.get("total", 0)),
        fatal_flaw=bool(parsed.get("fatal_flaw", False)),
        notes=str(parsed.get("notes", "")),
        retry_hints=list(parsed.get("retry_hints") or []),
        raw=raw,
    )


def critique_chapter(
    project: ProjectContext,
    chapter: Chapter,
    *,
    threshold_total: int = DEFAULT_THRESHOLD_TOTAL,
) -> list[CritiqueResult]:
    """Run the critic on every existing panel; print summary; write critiques.json."""
    if not chapter.scenes_json.exists():
        raise FileNotFoundError(f"missing {chapter.scenes_json}")
    cfg = json.loads(chapter.scenes_json.read_text(encoding="utf-8"))

    results: list[CritiqueResult] = []
    for scene in cfg["scenes"]:
        for panel in scene["panels"]:
            if panel.get("reuse_from"):
                continue
            pid = panel["panel_id"]
            scene_id = "_".join(pid.split("_")[:2])
            img = chapter.panels_dir / scene_id / f"{pid}_best.png"
            if not img.exists():
                continue
            r = critique_panel(project, chapter, panel, img)
            mark = "✓" if r.passed else "✗"
            print(f"  {mark} {pid}  total={r.total}/80  fatal={r.fatal_flaw}  {r.notes[:80]}")
            results.append(r)

    out_path = chapter.work_dir / "critiques.json"
    out_path.write_text(
        json.dumps([
            {
                "panel_id": r.panel_id,
                "scores": r.scores,
                "total": r.total,
                "fatal_flaw": r.fatal_flaw,
                "notes": r.notes,
                "retry_hints": r.retry_hints,
            }
            for r in results
        ], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failed = [r for r in results if not r.passed]
    print(f"\n  → {len(results)} panels critiqued, {len(failed)} below threshold (≥{threshold_total})")
    return results


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python -m src.critic <project_id> <chapter_id>", file=sys.stderr)
        return 1
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    critique_chapter(project, chapter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
