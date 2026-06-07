"""Compose English prompts from visual-grammar panel schemas."""
from __future__ import annotations

from typing import Any

from .project import ProjectContext


def _humanize(token: str) -> str:
    return token.replace("_", " ")


def compose_panel_prompt(
    project: ProjectContext,
    panel: dict[str, Any],
    setting: dict[str, str],
) -> str:
    shot = _humanize(panel["shot_type"])
    angle = _humanize(panel["camera_angle"])
    comp = _humanize(panel["composition"])
    eye = _humanize(panel["eye_line"])
    emo1 = _humanize(panel["emotion_primary"])
    emo2 = _humanize(panel["emotion_secondary"])
    lighting = _humanize(panel["lighting"])
    background = _humanize(panel["background_style"])
    aspect = panel["aspect_ratio"]

    chars = panel.get("characters_in_panel", [])
    subject_lines: list[str] = []
    for c in chars:
        char = project.character(c["id"])
        desc = char.description_en if char else project.description_for(c["id"])
        # Per-panel outfit override on character entry, else fall back to character default.
        outfit = c.get("outfit_en") or (char.outfit_en if char else "")
        if outfit:
            desc = f"{desc}, wearing {outfit}"
        pose = _humanize(c.get("pose", "natural_pose"))
        direction = _humanize(c.get("direction", "facing_camera"))
        subject_lines.append(f"subject: {desc}, {pose}, {direction}")

    location = setting.get("location", "")
    tod = setting.get("time_of_day", "")
    era = setting.get("era") or project.era

    extreme_hint = ""
    if panel["shot_type"] == "extreme_close_up_eyes":
        extreme_hint = "tight horizontal band framing on the eyes, most of the forehead above and the cheeks below cropped out of frame"

    intent = panel.get("intent")

    lines = [
        f"{shot}, {angle} angle, {comp} composition",
        *subject_lines,
        f"expression: {emo1}, with undertone of {emo2}",
        f"eye line: {eye}",
        f"setting: {location}, {tod}, {era}",
        f"lighting: {lighting}",
        f"background: {background}",
        *([f"intent: {intent}"] if intent else []),
        *([extreme_hint] if extreme_hint else []),
        f"style: {project.style_description}",
        f"aspect ratio: {aspect}",
        f"negative: {project.style_negative}",
    ]
    return ",\n".join(line for line in lines if line)
