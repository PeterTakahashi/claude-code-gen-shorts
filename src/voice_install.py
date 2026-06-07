"""Verify Aivis has all the voice models the project needs.

Usage:
  uv run python -m src.voice_install <project_id>

Checks `narrator.voice_style_id` plus every `characters[].voice_style_id` in
the project, and confirms each is exposed by `GET /speakers` on the running
Aivis engine. Prints a summary; returns non-zero if anything is missing.

For now this is verification-only. Auto-install via `POST /aivm_models/install`
can be added later (M9-ish, when we wire a UI for picking voices).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from .aivis import AivisClient, AivisError
from .project import ProjectContext, load


@dataclass
class VoiceCheckResult:
    required: set[int]
    installed: dict[int, tuple[str, str]]
    missing: set[int]

    @property
    def ok(self) -> bool:
        return not self.missing


def required_style_ids(project: ProjectContext) -> set[int]:
    ids: set[int] = set()
    if project.narrator_voice_style_id is not None:
        ids.add(project.narrator_voice_style_id)
    for c in project.characters:
        if c.voice_style_id is not None:
            ids.add(c.voice_style_id)
    return ids


def check(project: ProjectContext) -> VoiceCheckResult:
    client = AivisClient(endpoint=project.voice_endpoint)
    try:
        installed = client.installed_style_ids()
    except (AivisError, Exception) as e:
        raise RuntimeError(
            f"Cannot reach Aivis at {client.endpoint}. Is AivisSpeech-Engine running?\n  {e}"
        ) from e
    finally:
        client.close()
    required = required_style_ids(project)
    missing = required - set(installed.keys())
    return VoiceCheckResult(required=required, installed=installed, missing=missing)


def speaker_label(installed: dict[int, tuple[str, str]], style_id: int) -> str:
    if style_id in installed:
        spk, st = installed[style_id]
        return f"{spk} / {st}"
    return "(not installed)"


def report(project: ProjectContext, r: VoiceCheckResult) -> None:
    print(f"Aivis endpoint: {project.voice_endpoint or 'http://127.0.0.1:10101 (default)'}")
    print(f"Required style_ids: {len(r.required)}")
    used_by: dict[int, list[str]] = {}
    if project.narrator_voice_style_id is not None:
        used_by.setdefault(project.narrator_voice_style_id, []).append("narrator")
    for c in project.characters:
        if c.voice_style_id is not None:
            used_by.setdefault(c.voice_style_id, []).append(c.id)

    for sid in sorted(r.required):
        users = ", ".join(used_by.get(sid, []))
        mark = "  " if sid in r.installed else "❌"
        print(f"  {mark} {sid:>10}  {speaker_label(r.installed, sid):30s} ← {users}")

    if r.missing:
        print(f"\n❌ MISSING {len(r.missing)} style(s) — install them via Aivis UI or:")
        print(
            "    POST http://127.0.0.1:10101/aivm_models/install  with the .aivmx file\n"
            "    (download from https://hub.aivis-project.com)"
        )
    else:
        print(f"\n✅ all {len(r.required)} required style_ids are installed")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m src.voice_install <project_id>", file=sys.stderr)
        return 1
    project = load(sys.argv[1])
    try:
        r = check(project)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    report(project, r)
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
