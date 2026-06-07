You are adapting `{{title}}` chapter `{{chapter_id}}` ({{chapter_title}}) into a vertical-scroll webtoon. Read the chapter text and produce a `scenes.json` describing every panel.

The era is `{{era}}`. The character roster is in `characters.yaml`.

# Required first step

**Invoke the `webtoon-scenario-design` skill** via the Skill tool before authoring. It contains the visual-narrative rules (panel pacing, shot grammar, transition types, character economy, in_image_text, bubble_safe_zones, prose-to-comic condensation) that this output must follow. Re-read the skill mid-authoring whenever you face a design decision.

# What to produce

A JSON file with this shape:

```json
{
  "chapter_id": "{{chapter_id}}",
  "scenes": [
    {
      "id": "scene_01",
      "title": "<short scene description>",
      "source_text": "<the novel passage this scene covers>",
      "setting": {"location": "...", "time_of_day": "...", "era": "{{era}}"},
      "panels": [
        {
          "panel_id": "scene_01_p01",
          "shot_type": "wide_establishing",
          "camera_angle": "eye_level",
          "composition": "rule_of_thirds",
          "eye_line": "off_camera_left",
          "emotion_primary": "quiet_resignation",
          "emotion_secondary": "hollow_dread",
          "lighting": "soft_window_light_from_right",
          "background_style": "engawa_blurred",
          "aspect_ratio": "4:5",
          "intent": "establish the household at dusk",
          "treatment": "normal",
          "characters_in_panel": [
            {"id": "yozo_child", "pose": "sitting_seiza", "direction": "facing_camera"}
          ],
          "distance_to_next_panel": "breath"
        }
      ]
    }
  ]
}
```

# Field reference

- `shot_type`: `wide_establishing | medium | close_up | extreme_close_up_eyes | full_body | climax`
- `aspect_ratio`: typical `4:5`, `16:9` for establishing, `2:1` for ECU eyes, `1:2` for climax
- `treatment`: one of —
  - `normal` (color, default; ~90% of panels)
  - `symbolic_dark` (B&W high-contrast, climax/breakdown beat; ≤ 3 / chapter)
  - `monochrome` (deliberate B&W panel as stylistic punctuation)
  - `flashback_monochrome` (sepia memory; cluster 2-4 panels; bookend with `jump` gaps)
  - `dream_desaturated` (drained-color dream sequence)
  - `imagined_surreal` (color, with ghostly overlays; not really there)
  - `photograph` (diegetic in-world photograph rendered sepia)
- `distance_to_next_panel`: `tight (20px) | breath (80px) | jump (200px, scene change)`
- `characters_in_panel[].id` MUST match a character id in `characters.yaml`.

# Rules

1. Cover the **entire chapter** in scene order. Skip nothing — internal monologue must become panels too (use `treatment: imagined_surreal` or `extreme_close_up_eyes`).
2. Aim for **3–5 panels per scene**, **6–10 scenes per chapter** for a typical chapter length. Adjust to chapter length.
3. The **last panel of each scene** should have `distance_to_next_panel: jump`. Within a scene, mix `tight` (intense beats) and `breath` (default).
4. Use `extreme_close_up_eyes` strategically — once or twice per chapter at emotional pivots, not constantly.
5. `intent` should describe what the panel needs to *convey*, not literal description. The image-gen model uses other fields for the visual.
6. If a panel reuses an earlier panel exactly (e.g., a callback shot), use `"reuse_from": "<chapter_id>/panels/<scene_id>/<pid>_best.png"` instead of generating new specs.
7. Output **valid JSON only** — no markdown fences, no commentary. UTF-8.
