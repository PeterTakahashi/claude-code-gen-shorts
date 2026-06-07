"""Load a project's input/novel.txt and split into per-chapter files.

Sources:
  - input/novel.txt is plain UTF-8 text (already de-Aozora'd)
  - project.yaml > chapters[] specifies per-chapter start_marker / end_marker

For HTML inputs, run `strip_aozora_html()` first:
    text = strip_aozora_html(html_path.read_bytes())
    project_dir / "input" / "novel.txt".write_text(text, encoding="utf-8")
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .project import Chapter, ProjectContext, load


RUBY_RT = re.compile(r"<rt>.*?</rt>", re.DOTALL)
RUBY_RP = re.compile(r"<rp>.*?</rp>", re.DOTALL)
TAG = re.compile(r"<[^>]+>", re.DOTALL)
RUBY_BRACKETS = re.compile(r"《[^》]*》")
ANNOTATION = re.compile(r"［[^］]*］")
PIPE = re.compile(r"｜")
MULTI_NEWLINE = re.compile(r"\n{3,}")


def strip_aozora_html(raw: bytes) -> str:
    """De-rubify Aozora HTML/Shift_JIS bytes into clean UTF-8 text."""
    try:
        html = raw.decode("shift_jis")
    except UnicodeDecodeError:
        html = raw.decode("cp932", errors="replace")
    text = RUBY_RT.sub("", html)
    text = RUBY_RP.sub("", text)
    text = TAG.sub("", text)
    text = RUBY_BRACKETS.sub("", text)
    text = ANNOTATION.sub("", text)
    text = PIPE.sub("", text)
    text = text.replace("&nbsp;", " ")
    text = MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def extract_chapter(full_text: str, chapter: Chapter) -> str:
    """Extract one chapter's text from a novel using start/end markers.

    If start_marker is None, the chapter is the entire novel (single-chapter mode).
    If end_marker is None, the chapter runs to end of file.
    """
    if chapter.start_marker is None:
        return full_text.strip()
    start = full_text.find(chapter.start_marker)
    if start < 0:
        raise ValueError(
            f"chapter {chapter.id!r}: start_marker {chapter.start_marker!r} not found in novel"
        )
    end = len(full_text)
    if chapter.end_marker:
        e = full_text.find(chapter.end_marker, start + len(chapter.start_marker))
        if e >= 0:
            end = e
    return full_text[start:end].strip()


def split_chapters(project: ProjectContext, force: bool = False) -> list[Path]:
    """Split input/novel.txt into work/chapters/<id>/novel.txt for each chapter.

    Idempotent — skips chapters whose novel.txt already exists, unless force=True.
    Returns the list of chapter txt paths.
    """
    if not project.input_novel.exists():
        raise FileNotFoundError(f"missing {project.input_novel}")
    full = project.input_novel.read_text(encoding="utf-8")

    out: list[Path] = []
    for chapter in project.chapters:
        dst = chapter.novel_txt
        if dst.exists() and not force:
            out.append(dst)
            continue
        text = extract_chapter(full, chapter)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        print(f"  → {dst}  ({len(text)} chars)")
        out.append(dst)
    return out


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.novel_loader <project_id>", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    paths = split_chapters(project, force="--force" in sys.argv)
    print(f"\n✅ {len(paths)} chapter file(s) written under {project.project_dir}/work/chapters/")


if __name__ == "__main__":
    main()
