"""Codex CLI wrapper for scenario review.

Runs `codex exec` with prompts/review_scenario.md as the instruction. Codex
reads scenes.json/bubbles.json/novel.txt/characters.yaml from disk and writes
a structured review markdown to `work/chapters/<ch>/reviews/round_<N>.md`.

Exit code: 0 if review file is written, non-zero otherwise.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .project import Chapter, ProjectContext, REPO_ROOT, load


PROMPTS_DIR = REPO_ROOT / "prompts"


def _ensure_codex_on_path() -> None:
    if shutil.which("codex") is None:
        raise RuntimeError(
            "Codex CLI ('codex') not found on PATH. Install Codex CLI or run "
            "the review prompt manually and drop the markdown into the reviews/ dir."
        )


def _next_round(reviews_dir: Path) -> int:
    if not reviews_dir.exists():
        return 1
    existing = [p.name for p in reviews_dir.glob("round_*.md")]
    nums = []
    for n in existing:
        try:
            nums.append(int(n.replace("round_", "").replace(".md", "")))
        except ValueError:
            continue
    return (max(nums) if nums else 0) + 1


def review_chapter(project: ProjectContext, chapter: Chapter, *, force: bool = False) -> Path:
    """Run one review round and return the path of the written markdown."""
    _ensure_codex_on_path()

    reviews_dir = chapter.work_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    round_n = _next_round(reviews_dir) if force else max(1, _next_round(reviews_dir) - 1) or 1
    if not force and (reviews_dir / f"round_{round_n}.md").exists():
        existing = reviews_dir / f"round_{round_n}.md"
        print(f"  ✓ existing review: {existing}")
        return existing

    out_path = reviews_dir / f"round_{round_n}.md"

    template = (PROMPTS_DIR / "review_scenario.md").read_text(encoding="utf-8")
    body = template
    for k, v in {
        "chapter_id": chapter.id,
        "title": project.title_ja,
        "round": str(round_n),
        "chapter_novel_path": str(chapter.novel_txt),
        "scenes_json_path": str(chapter.scenes_json),
        "bubbles_json_path": str(chapter.bubbles_json),
        "characters_yaml_path": str(project.characters_yaml),
        "output_path": str(out_path),
    }.items():
        body = body.replace(f"{{{{{k}}}}}", v)

    print(f"\n[codex] reviewing {chapter.id} → {out_path}")
    cmd = ["codex", "exec", "--skip-git-repo-check", body]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"codex exec exited with status {proc.returncode}")
    if not out_path.exists():
        raise RuntimeError(
            f"codex did not write {out_path}. Re-run with --force, or run "
            "the prompt manually and save the markdown."
        )
    return out_path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python -m src.codex_review <project_id> <chapter_id> [--force]", file=sys.stderr)
        return 1
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    force = "--force" in sys.argv
    review_chapter(project, chapter, force=force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
