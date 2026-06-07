You are authoring `bubbles.json` for chapter `{{chapter_id}}` of `{{title}}`. **You will be given the actual rendered panel images** — your job is to look at each panel and decide:

1. Where the bubbles go (without covering faces or focal points)
2. What text each bubble contains (matched to the chapter's source novel)
3. What ElevenLabs sound-effect prompts go with each panel
4. What scene-level BGM (ambience) plays per scene

# Required first step

**Invoke the `webtoon-scenario-design` skill** via the Skill tool before authoring. It is the single source of truth for bubble layout (reading order, caption types, safe-zone use, text density), SFX/BGM design, and onomatopoeia rules. Re-read the relevant section whenever you make a placement or audio decision.

# Inputs you have

- `scenes.json` — every panel's shot/composition spec, plus any `in_image_text[]` (擬音語/環境テキスト already drawn into the image) and `bubble_safe_zones[]` (regions deliberately kept quiet for bubble placement).
- The chapter's source `novel.txt` — the canonical text the bubbles should reflect.
- All panel images at `panels/<scene_id>/<panel_id>_best.png`.

**Read the panel images.** Do not guess positions from text alone. The whole point of this stage is that you have visual access.

# What to produce

A single JSON file with this exact shape:

```jsonc
{
  "panels": [
    {
      "panel_id": "scene_01_p01",
      "bubbles": [
        {
          "type": "narration_box | monologue_box | speech | thought",
          "speaker": "narrator | <character_id>",
          "text": "ああ、そうか、自分には...",
          "x_pct": 70,
          "y_pct": 8,
          "width_pct": 26,
          "tail_target": null,
          "font_size_pt": 14,
          "vertical_text": true,
          "anchor_safe_zone_idx": 0
        }
      ],
      "sfx": [
        {
          "id": "sfx_01",
          "elevenlabs_prompt": "soft footsteps on wooden floorboards, traditional Japanese house",
          "duration_s": 1.5,
          "start_offset_s": 0.0,
          "volume_db": -8,
          "prompt_influence": 0.4
        }
      ],
      "bgm_cue": null
    }
  ],
  "scene_bgm": [
    {
      "scene_id": "scene_01",
      "elevenlabs_prompt": "quiet melancholic ambient drone, distant cicadas, evening",
      "volume_db": -18,
      "loop": true,
      "fade_in_s": 0.8,
      "fade_out_s": 1.2,
      "extra_tail_s": 1.5,
      "prompt_influence": 0.2
    }
  ],
  "font_main": "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
  "font_index": 0,
  "font_scale": 1.5
}
```

# Rules — bubble placement

- **Look at the actual panel image** before deciding x_pct/y_pct. Avoid the face, eyes, and primary focal point.
- Prefer the regions listed in `scenes.json.<panel>.bubble_safe_zones[]`. Reference them by index in `anchor_safe_zone_idx`.
- Reading order is right-top → left-bottom (Japanese vertical text convention). Multiple bubbles in one panel should follow that order.
- `narration_box` and `monologue_box` are rectangular boxes with no tail — set `tail_target: null`.
- `speech` and `thought` need `tail_target: {"x_pct": ..., "y_pct": ...}` pointing at the speaker's mouth or head.
- `vertical_text: true` for Japanese (default). Set false only for English captions.
- `font_size_pt: 14` is a good default; bump to 16 for emphatic single lines, drop to 12 for crowded boxes.

# Rules — text content

- The text must reflect the source novel — do not invent dialogue or paraphrase aggressively.
- Use plain modern Japanese kana/kanji. No furigana brackets.
- `narration_box` carries the narrator's third-person framing; `monologue_box` carries the protagonist's internal voice; `speech` is spoken aloud by `speaker`; `thought` is silent thought.
- `speaker` for narration/monologue is `"narrator"`. For speech/thought it must be a `<character_id>` from `characters.yaml`.

# Rules — SFX (sound effects, audio side)

- Add `sfx[]` entries for sounds that should play during the panel, even if there is no in_image_text drawn for them.
- If a panel's `scenes.json.in_image_text[]` has `kind: sfx` with `linked_sfx_id`, the matching `bubbles.json.<panel>.sfx[].id` must equal that `linked_sfx_id` (so visual text and audio cue are paired).
- ElevenLabs Sound Effects API caps a single call at ~22 seconds. Keep `duration_s` ≤ 22; longer atmospheres go in `scene_bgm`, not `sfx`.
- Use English prompts to ElevenLabs (`elevenlabs_prompt`). Be specific about era/material (e.g., "wooden floorboards, traditional Japanese house").
- `start_offset_s` is when the SFX starts within the panel's voice clip; `volume_db` is its mix level. The mixer (M4) reads these later — for now just pick reasonable defaults (-8 to -3 dB for foreground SFX, -12 to -16 dB for background).

# Rules — scene BGM

- One `scene_bgm` entry per scene that needs ambience. Skip scenes that should be silent (e.g., a stark monologue).
- The ambience plays under all the panels of that scene. Use a `bgm_cue` of `"fade_out"` on the last panel of a scene if you want a pre-emptive fade before the next scene's BGM starts.
- `volume_db: -18` is a safe default (BGM should be quieter than voice).
- `prompt_influence: 0.2` keeps the ambience subtle; raise to 0.4 for more deliberate atmospheres.

# Output

Write **valid JSON only** to the path you are told. No markdown fences, no preamble, no commentary. UTF-8.
