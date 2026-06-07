"""Layer 3: verify Aivis-generated voices with Whisper.

For each per-panel voice mp3:
  1. Transcribe with `whisper` CLI (openai-whisper). Japanese mode.
  2. Normalize both intended text and transcript to hiragana via pykakasi.
  3. Compute Levenshtein-based similarity with rapidfuzz.
  4. Anything below `voice.similarity_threshold` (default 0.88) is flagged in
     `<chapter>/voice_review.md`, with a heuristic suggestion of which kanji
     in the original text might be the culprit.

Output:
  - work/chapters/<ch>/voice_review.md          (human-readable report)
  - work/chapters/<ch>/voice_review.json        (machine-readable, mtime-driven)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from pykakasi import kakasi
from rapidfuzz.distance import Levenshtein

from .project import Chapter, ProjectContext, load


_KKS = kakasi()
_PUNCT = re.compile(r'[、。「」『』！？!?,.\s—…・"\']+')
_KANJI = re.compile(r"[一-龥々]+")


def _to_hira(text: str) -> str:
    text = _PUNCT.sub("", text)
    return "".join(p["hira"] for p in _KKS.convert(text))


def _similarity(a: str, b: str) -> float:
    if not a:
        return 1.0 if not b else 0.0
    return 1.0 - (Levenshtein.distance(a, b) / max(len(a), len(b)))


@dataclass
class VoiceFinding:
    panel_id: str
    bubble_idx: int
    intended: str
    transcript: str
    intended_hira: str
    transcript_hira: str
    similarity: float
    suggested_lexicon: list[dict]


def _whisper_transcribe(wav_path: Path, model: str = "small") -> str:
    """Run openai-whisper CLI on a single audio file, return concatenated text."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cmd = [
            "whisper", str(wav_path),
            "--language", "Japanese",
            "--model", model,
            "--output_dir", str(td),
            "--output_format", "txt",
            "--verbose", "False",
            "--fp16", "False",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"whisper failed:\n{r.stderr[-1000:]}")
        txt_files = list(td.glob("*.txt"))
        if not txt_files:
            return ""
        return txt_files[0].read_text(encoding="utf-8").strip()


def _suggest_lexicon_entries(intended: str, transcript: str) -> list[dict]:
    """Heuristic: kanji words in intended text that disappear in transcript hira are suspect."""
    transcript_hira = _to_hira(transcript)
    suggestions: list[dict] = []
    seen: set[str] = set()
    for m in _KANJI.finditer(intended):
        kanji = m.group(0)
        if kanji in seen:
            continue
        seen.add(kanji)
        kanji_hira = _to_hira(kanji)
        if kanji_hira and kanji_hira not in transcript_hira:
            suggestions.append({"surface": kanji, "reading_guess": kanji_hira, "kind": "noun"})
    return suggestions


def verify_chapter(project: ProjectContext, chapter: Chapter, *, threshold: float = 0.88, model: str | None = None, force: bool = False) -> list[VoiceFinding]:
    if not chapter.bubbles_json.exists():
        raise FileNotFoundError(f"missing {chapter.bubbles_json}")
    bubbles_cfg = json.loads(chapter.bubbles_json.read_text(encoding="utf-8"))
    panels = bubbles_cfg.get("panels", [])

    cfg_voice = project.raw.get("voice", {}) or {}
    threshold = float(cfg_voice.get("similarity_threshold", threshold))
    whisper_model = model or cfg_voice.get("whisper", {}).get("model", "small")

    review_md = chapter.voice_review_md if hasattr(chapter, "voice_review_md") else (chapter.work_dir / "voice_review.md")
    review_json = chapter.work_dir / "voice_review.json"

    if review_md.exists() and review_json.exists() and not force:
        try:
            cached = json.loads(review_json.read_text(encoding="utf-8"))
            findings = [VoiceFinding(**f) for f in cached.get("findings", [])]
            print(f"  ✓ cached: {len(findings)} flagged finding(s) under threshold {threshold}")
            return findings
        except Exception:
            pass

    findings: list[VoiceFinding] = []
    for p in panels:
        pid = p["panel_id"]
        wav = chapter.audio_dir / f"{pid}.mp3"
        if not wav.exists():
            continue
        # Re-synthesize the *concatenated* intended text by joining bubble texts in order.
        bubbles = p.get("bubbles") or []
        if not bubbles:
            continue
        intended_full = "".join(b.get("text", "") for b in bubbles).strip()
        if not intended_full:
            continue
        try:
            transcript = _whisper_transcribe(wav, model=whisper_model)
        except Exception as e:
            print(f"  ⚠ whisper failed on {pid}: {e}")
            continue

        a = _to_hira(intended_full)
        b = _to_hira(transcript)
        sim = _similarity(a, b)
        flag = sim < threshold
        marker = "❌" if flag else "✓"
        print(f"  {marker} {pid}  sim={sim:.3f}  intended={len(intended_full)} transcript={len(transcript)}")
        if flag:
            findings.append(VoiceFinding(
                panel_id=pid,
                bubble_idx=0,
                intended=intended_full,
                transcript=transcript,
                intended_hira=a,
                transcript_hira=b,
                similarity=sim,
                suggested_lexicon=_suggest_lexicon_entries(intended_full, transcript),
            ))

    # Write report.
    review_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# voice_review — {chapter.id} ({len(findings)} flagged / threshold={threshold})",
        "",
        "Flagged panels (similarity below threshold). Decide whether each suggested",
        "lexicon entry should be merged into `lexicon.yaml`. Then re-run:",
        "  uv run python -m src.narrate <project> <chapter> --force",
        "",
    ]
    for f in findings:
        lines.append(f"## {f.panel_id} (similarity {f.similarity:.3f})")
        lines.append(f"- **intended**: {f.intended}")
        lines.append(f"- **transcript**: {f.transcript}")
        lines.append(f"- intended hira:  `{f.intended_hira}`")
        lines.append(f"- transcript hira: `{f.transcript_hira}`")
        if f.suggested_lexicon:
            lines.append(f"- suggested lexicon entries:")
            for s in f.suggested_lexicon:
                lines.append(f"  - `{{ surface: {s['surface']}, reading: {s['reading_guess']}, kind: {s['kind']} }}`")
        lines.append("")
    review_md.write_text("\n".join(lines), encoding="utf-8")
    review_json.write_text(
        json.dumps({"threshold": threshold, "findings": [asdict(f) for f in findings]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n  ✓ wrote {review_md}  ({len(findings)} flagged)")
    return findings


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python -m src.voice_verify <project_id> <chapter_id> [--force] [--model=small|medium|large-v3]", file=sys.stderr)
        sys.exit(1)
    project = load(sys.argv[1])
    chapter = project.chapter(sys.argv[2])
    force = "--force" in sys.argv
    model = next((a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("--model=")), None)
    findings = verify_chapter(project, chapter, force=force, model=model)
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
