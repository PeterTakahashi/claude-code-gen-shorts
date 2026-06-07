"""ProjectContext — load project.yaml + characters.yaml and expose paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = REPO_ROOT / "projects"


@dataclass
class Chapter:
    id: str
    title: str
    start_marker: str | None
    end_marker: str | None
    project_dir: Path

    @property
    def work_dir(self) -> Path:
        return self.project_dir / "work" / "chapters" / self.id

    @property
    def output_dir(self) -> Path:
        return self.project_dir / "output" / self.id

    @property
    def novel_txt(self) -> Path:
        return self.work_dir / "novel.txt"

    @property
    def scenes_json(self) -> Path:
        return self.work_dir / "scenes.json"

    @property
    def bubbles_json(self) -> Path:
        return self.work_dir / "bubbles.json"

    @property
    def panels_dir(self) -> Path:
        return self.work_dir / "panels"

    @property
    def bubbled_dir(self) -> Path:
        return self.work_dir / "bubbled"

    @property
    def audio_dir(self) -> Path:
        # Voice (per-panel TTS) lives at the root of audio/ for back-compat with
        # existing artifacts. M4 (3-track mix) may move it to audio/voice/.
        return self.work_dir / "audio"

    @property
    def audio_sfx_dir(self) -> Path:
        return self.work_dir / "audio" / "sfx"

    @property
    def audio_bgm_dir(self) -> Path:
        return self.work_dir / "audio" / "bgm"

    @property
    def audio_mix_dir(self) -> Path:
        return self.work_dir / "audio" / "mix"

    @property
    def audio_master_wav(self) -> Path:
        return self.audio_mix_dir / "chapter_master.wav"

    @property
    def voice_review_md(self) -> Path:
        return self.work_dir / "voice_review.md"

    @property
    def reviews_dir(self) -> Path:
        return self.work_dir / "reviews"

    @property
    def pages_dir(self) -> Path:
        return self.work_dir / "pages"

    @property
    def video_segs_dir(self) -> Path:
        return self.work_dir / "video_segs"

    @property
    def panel_positions_json(self) -> Path:
        return self.work_dir / "panel_positions.json"

    @property
    def webtoon_for_video_png(self) -> Path:
        return self.work_dir / "webtoon_for_video.png"

    @property
    def webtoon_png(self) -> Path:
        return self.output_dir / "webtoon.png"

    @property
    def webtoon_scroll_mp4(self) -> Path:
        # Legacy / archived; new flow writes master_mp4 instead.
        return self.output_dir / "webtoon_scroll.mp4"

    @property
    def master_mp4(self) -> Path:
        return self.output_dir / "master.mp4"

    @property
    def subtitles_srt(self) -> Path:
        return self.output_dir / "subtitles.srt"

    @property
    def silent_chapter_mp4(self) -> Path:
        return self.work_dir / "silent_chapter.mp4"

    @property
    def padded_panels_dir(self) -> Path:
        return self.work_dir / "padded"

    @property
    def video_clips_dir(self) -> Path:
        return self.work_dir / "video_clips"

    @property
    def subtitles_json(self) -> Path:
        return self.audio_dir / "_subtitles.json"


@dataclass
class Character:
    id: str
    description_en: str
    outfit_en: str
    voice_style_id: int | None         # Aivis speaker style_id (integer)
    voice_instructions: str | None     # description-only, used to pick Aivis style
    selected_candidate: int | None
    name_ja: str | None = None
    voice_speed: float = 1.0
    voice_pitch: float = 0.0
    voice_intonation: float = 1.0
    expressions: list[str] = field(default_factory=list)
    poses: list[str] = field(default_factory=list)

    def candidates_dir(self, project_dir: Path) -> Path:
        return project_dir / "characters" / self.id / "candidates"

    def char_dir(self, project_dir: Path) -> Path:
        return project_dir / "characters" / self.id

    def selected_png(self, project_dir: Path) -> Path:
        return self.char_dir(project_dir) / "selected.png"

    def stylesheet_turnaround(self, project_dir: Path) -> Path:
        return self.char_dir(project_dir) / "stylesheet_turnaround.png"

    def stylesheet_expression(self, project_dir: Path) -> Path:
        return self.char_dir(project_dir) / "stylesheet_expressions.png"


@dataclass
class ProjectContext:
    id: str
    project_dir: Path
    raw: dict[str, Any]
    characters: list[Character]
    chapters: list[Chapter]

    # ---- Convenience accessors mirroring project.yaml shape ----
    @property
    def title_ja(self) -> str:
        return self.raw.get("title_ja", self.id)

    @property
    def title_en(self) -> str:
        return self.raw.get("title_en", self.id)

    @property
    def language(self) -> str:
        return self.raw.get("language", "ja")

    @property
    def era(self) -> str:
        return self.raw.get("era", "")

    @property
    def locale_hint(self) -> str:
        return self.raw.get("locale_hint", "")

    @property
    def style_description(self) -> str:
        return self.raw.get("style", {}).get("description", "")

    @property
    def style_negative(self) -> str:
        return self.raw.get("style", {}).get("negative", "")

    @property
    def narrator_voice_style_id(self) -> int | None:
        v = self.raw.get("narrator", {}).get("voice_style_id")
        return int(v) if v is not None else None

    @property
    def narrator_voice_speed(self) -> float:
        return float(self.raw.get("narrator", {}).get("voice_speed", 1.0))

    @property
    def narrator_instructions(self) -> str:
        return self.raw.get("narrator", {}).get("instructions", "")

    @property
    def voice_endpoint(self) -> str | None:
        return self.raw.get("voice", {}).get("endpoint")

    @property
    def bubble_font_path(self) -> str:
        return self.raw.get("bubbles", {}).get("font_path", "")

    @property
    def bubble_font_index(self) -> int:
        return int(self.raw.get("bubbles", {}).get("font_index", 0))

    @property
    def bubble_font_scale(self) -> float:
        return float(self.raw.get("bubbles", {}).get("font_scale", 1.0))

    @property
    def webtoon_width(self) -> int:
        return int(self.raw.get("webtoon", {}).get("width_px", 800))

    @property
    def panel_gap_px(self) -> dict[str, int]:
        d = self.raw.get("webtoon", {}).get("panel_gap_px") or {}
        return {"tight": 20, "breath": 80, "jump": 200, **d}

    # ---- Paths ----
    @property
    def project_yaml(self) -> Path:
        return self.project_dir / "project.yaml"

    @property
    def characters_yaml(self) -> Path:
        return self.project_dir / "characters.yaml"

    @property
    def lexicon_yaml(self) -> Path:
        return self.project_dir / "lexicon.yaml"

    def load_lexicon(self):
        """Lazy-load the project lexicon. Empty Lexicon if no lexicon.yaml."""
        from . import lexicon as _lex
        return _lex.load(self.lexicon_yaml if self.lexicon_yaml.exists() else None)

    @property
    def input_novel(self) -> Path:
        return self.project_dir / "input" / "novel.txt"

    # ---- Lookups ----
    def chapter(self, chapter_id: str) -> Chapter:
        for ch in self.chapters:
            if ch.id == chapter_id:
                return ch
        raise KeyError(f"chapter {chapter_id!r} not in project {self.id}")

    def character(self, char_id: str) -> Character | None:
        for c in self.characters:
            if c.id == char_id:
                return c
        return None

    def description_for(self, char_id: str) -> str:
        c = self.character(char_id)
        if c is None:
            return f"an unnamed {char_id.replace('_', ' ')} figure in {self.era or 'the setting'}"
        return c.description_en

    def voice_for(self, speaker: str) -> tuple[int | None, float, float, float, str]:
        """Resolve speaker → (style_id, speed, pitch, intonation, instructions).

        Falls back to narrator config when the speaker is unknown or has no voice.
        """
        narr_id = self.narrator_voice_style_id
        narr_speed = self.narrator_voice_speed
        narr_inst = self.narrator_instructions
        if speaker == "narrator":
            return narr_id, narr_speed, 0.0, 1.0, narr_inst
        c = self.character(speaker)
        if c is None or c.voice_style_id is None:
            return narr_id, narr_speed, 0.0, 1.0, narr_inst
        return (
            c.voice_style_id,
            c.voice_speed,
            c.voice_pitch,
            c.voice_intonation,
            c.voice_instructions or narr_inst,
        )

    def resolve_path(self, ref: str) -> Path:
        """Resolve a path string from JSON (scenes.json reuse_from etc.).

        - Absolute → returned as-is.
        - Relative → resolved against the project directory first, falling back
          to the repo root for backwards-compat with old "work/..." references.
        """
        p = Path(ref)
        if p.is_absolute():
            return p
        proj_rel = self.project_dir / ref
        if proj_rel.exists():
            return proj_rel
        return REPO_ROOT / ref


def load(project_id_or_dir: str | Path) -> ProjectContext:
    """Load a project by id (looks under projects/) or by explicit directory."""
    p = Path(project_id_or_dir)
    project_dir = p if p.is_absolute() or p.exists() else PROJECTS_ROOT / str(project_id_or_dir)
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"project directory not found: {project_dir}")

    project_yaml = project_dir / "project.yaml"
    if not project_yaml.exists():
        raise FileNotFoundError(f"missing {project_yaml}")
    raw = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}

    chapters_data = raw.get("chapters") or []
    if not chapters_data:
        # Whole-novel-as-one-chapter mode.
        chapters_data = [{"id": "main", "title": raw.get("title_ja", "main"), "start_marker": None, "end_marker": None}]
    chapters = [
        Chapter(
            id=c["id"],
            title=c.get("title", c["id"]),
            start_marker=c.get("start_marker"),
            end_marker=c.get("end_marker"),
            project_dir=project_dir,
        )
        for c in chapters_data
    ]

    characters_yaml = project_dir / "characters.yaml"
    if characters_yaml.exists():
        chars_raw = yaml.safe_load(characters_yaml.read_text(encoding="utf-8")) or {}
        chars_data = chars_raw.get("characters") or []
    else:
        chars_data = []
    characters = [
        Character(
            id=c["id"],
            description_en=c.get("description_en", ""),
            outfit_en=c.get("outfit_en", ""),
            voice_style_id=int(c["voice_style_id"]) if c.get("voice_style_id") is not None else None,
            voice_speed=float(c.get("voice_speed", 1.0)),
            voice_pitch=float(c.get("voice_pitch", 0.0)),
            voice_intonation=float(c.get("voice_intonation", 1.0)),
            voice_instructions=c.get("voice_instructions"),
            selected_candidate=c.get("selected_candidate"),
            name_ja=c.get("name_ja"),
            expressions=list(c.get("expressions") or []),
            poses=list(c.get("poses") or []),
        )
        for c in chars_data
    ]

    return ProjectContext(
        id=raw.get("id", project_dir.name),
        project_dir=project_dir,
        raw=raw,
        characters=characters,
        chapters=chapters,
    )
