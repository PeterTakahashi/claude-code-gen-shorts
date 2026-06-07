---
name: webtoon-scenario-design
description: Visual-narrative design rules for adapting a novel into a vertical-scroll webtoon. Invoke when authoring scenes.json (panel structure, shot grammar, in-image text, safe zones) or bubbles.json (dialogue placement, SFX/BGM cues) for a novel-to-video pipeline. Covers panel pacing, Scott McCloud transitions, shot types, eye-line continuity, dialogue layout, onomatopoeia, and prose-to-comic condensation.
---

# Webtoon scenario design — actionable rules

You are designing the visual & textual plan for a webtoon adapted from prose. The output is `scenes.json` (visual layer) and/or `bubbles.json` (text + audio layer) consumed by `webtoon-gen`. **Apply the rules below; do not theorize about them.**

## 1. Format fundamentals

- **Vertical scroll, mobile-first.** Canvas width 800 px (we render at 800; Webtoon platform standard is 800×1280 per upload chunk).
- **Full color is the default.** Modern webtoons are color works. Monochrome is a per-panel narrative beat (flashback, climax breakdown, etc.) selected via `treatment` — see §12. Do NOT make a whole chapter monochrome unless the project's `style.description` explicitly says so.
- **One main focal point per panel.** Mobile screens are small; clarity > density.
- **Panel gaps = pacing.** `tight (20px)` accelerates, `breath (80px)` is the default beat, `jump (200px)` signals scene change. Use vertical white space deliberately — large gaps create suspense, large panels followed by tiny ones create shock.
- **Stack vertically, not in a 4-panel grid.** Webtoon ≠ traditional manga page; never lay out side-by-side panels.

## 2. Panel-to-panel transitions (Scott McCloud's six)

| Transition | When to use | Gap |
|---|---|---|
| **moment-to-moment** | Subtle change in same shot (eyes narrowing) | `tight` |
| **action-to-action** | Most common; one subject, sequential beats | `breath` |
| **subject-to-subject** | Same scene, shift focus to another person/object | `breath` |
| **aspect-to-aspect** | Mood pieces — different facets of one moment (rain → window → tea cup → face). **Manga's signature rhythm.** Use 2–4× per chapter | `tight` between, `breath` to next |
| **scene-to-scene** | Time/place jump | `jump` |
| **non-sequitur** | Avoid. |

Internal-monologue-heavy novels (e.g., 人間失格) → **lean on aspect-to-aspect** to externalize inner state without a literal close-up of a face for ten panels.

## 3. Shot grammar

| `shot_type` | Use | Notes |
|---|---|---|
| `wide_establishing` | Open scene, place character in environment | aspect 16:9 typical |
| `full_body` | Costume / posture / silhouette | 3:4 |
| `medium` | Head-to-hips, expression + gesture | 4:5 default |
| `close_up` | Face, hands, key object | 4:5 |
| `extreme_close_up_eyes` | Emotional pivot. **Max 1–2 per chapter.** | 2:1 horizontal band |
| `climax` | Splash-style impact panel | 1:2 vertical |

## 4. Camera angle semantics

- `eye_level` — neutral baseline (default)
- `low_angle` — power, dominance, confidence
- `high_angle` — weakness, smallness, entrapment
- `dutch / tilted` — unease, vertigo (sparingly; horror/breakdown)
- `over_shoulder` — dialogue framing, embeds POV without ECU
- `from_behind` — alienation, mystery, opening shots

## 5. Continuity rules — non-negotiable

- **180° axis.** When two characters are talking, draw an imaginary line between them; keep all panels on one side of that line. Crossing it disorients the reader.
- **Eye-line match.** If panel A's character looks frame-right, panel B should place the looked-at object frame-right (so the gaze "lands" correctly in the reader's mental space).
- **Shot-reverse-shot.** Dialogue alternation A → B → A. Each panel's framing must be consistent with the 180° axis.
- **Match-on-action.** Across `action-to-action` transitions, body part being moved should be consistent (raised arm in panel A continues raised in panel B, not suddenly lowered).

## 6. Dialogue & speech bubble layout

### Reading order (Japanese)
- **Right-top → left-bottom.** Number bubbles in this order regardless of speaker.
- Within a single bubble, **vertical text** (column right-to-left) is the default for `monologue_box` / `narration_box` / Japanese `speech`. English captions use horizontal.

### Caption types
| Type | Shape | Use |
|---|---|---|
| `narration_box` | Rectangle, no tail | 3rd-person framing, scene-setting |
| `monologue_box` | Rectangle, no tail | Protagonist's inner voice (preferred over thought balloon for prose adaptations) |
| `speech` | Oval + tail at speaker's mouth | Spoken aloud |
| `thought` | Cloud + bubble trail | Silent thought (use sparingly; cartoony) |

### Placement
- **Never cover faces or focal points.** Use `bubble_safe_zones[]` declared in scenes.json.
- Multiple bubbles: stack vertically on one side (right or left), or follow a top-right → bottom-left diagonal.
- Keep individual bubbles **short and purposeful**; long monologues split into multiple boxes (each ≤ ~70 chars), placed on the same vertical column.

### Text density
- Short panels: 1 bubble, ≤ 30 chars
- Establishing panels: 1 narration_box, ≤ 90 chars
- Climax / silence: 0 bubbles (let the image speak)
- Average **40 % of a chapter's panels should be silent** — webtoon pacing is image-led.

### Subtitle splitting (automatic at TTS time)
The pipeline auto-splits any bubble whose text exceeds **35 full-width Japanese characters** (one subtitle line) into multiple chunks at natural break points (sentence end → comma → hard cut). Each chunk becomes its own Aivis synthesis call and its own on-screen subtitle. So you can safely write 80–120-char monologue boxes when authoring `bubbles.json` — the runtime will split them. There's no need to pre-split unless you want explicit control over where breaks happen (in which case provide multiple `bubbles[]` entries already split).

## 7. In-image text (擬音語 / SFX / diegetic)

**Drawn into the panel by nanobanana, NOT in a bubble.**

- **Three categories of Japanese onomatopoeia:**
  - `giseigo` (擬声語): people/animals — ワーン、ワン
  - `giongo` (擬音語): inanimate sounds — ガタッ、サッ、ザワザワ
  - `gitaigo` (擬態語): visual/sensory — ドキドキ、シーン
- **Katakana**: mechanical, loud, foreign, energetic
- **Hiragana**: soft, childlike, emotional
- **Length rule (nanobanana reliability):** 1–4 chars only. Long sequences like ザワザワザワザワ become unreadable in image gen.
- **Position & energy match:** `style_hint` should describe brushwork that fits intensity. A whisper (シーン) → soft thin strokes; a slam (バンッ) → bold thick angular strokes.
- **Pair with audio.** When you place an SFX onomatopoeia in `scenes.json.in_image_text[]`, ensure `bubbles.json.panel.sfx[]` has a matching entry with the same `linked_sfx_id` so visual and audio fire together.

## 8. Bubble safe zones

`bubble_safe_zones[]` tells nanobanana to leave specific regions visually quiet (light bg, no faces, no detail) so PIL bubble overlay won't collide with art.

- Define ≥ 1 zone per panel that has a bubble.
- Min size: `w_pct ≥ 20`, `h_pct ≥ 12` so text fits.
- Top horizontal band (y=2-18%, w=96%) is the safest default for narration_box.
- **Do not** place safe zones over composition focal points implied by `composition` field.

## 9. Prose-to-comic condensation

The biggest risk in adapting a novel is **carrying over too much text**.

- A 2-page prose passage → 3–6 panels typically. **Drop adjectives the image already conveys.**
- "He smiled with a sadness that did not reach his eyes" → don't paraphrase; render it as `extreme_close_up_eyes` + `emotion_primary: performative_smile / emotion_secondary: hollow`.
- For internal-monologue-heavy passages, **split a long thought into multiple monologue_box bubbles distributed across multiple panels** with aspect-to-aspect imagery between them.
- "Show, don't narrate": clenched fists / averted gaze / lit cigarette > 3 sentences of inner reflection.
- Cut redundant attribution. If the panel shows who's talking, the bubble doesn't need "he said".

## 10. Pacing tools at your disposal

| Want to slow down | Want to speed up |
|---|---|
| Larger panel (taller) | Smaller panel |
| `breath` or `jump` gap | `tight` gap |
| `aspect-to-aspect` chain | `action-to-action` |
| `extreme_close_up_eyes` (rare) | `medium` shot streak |
| Silent panel (no bubble) | 1-bubble panel |
| `treatment: symbolic_dark` | `treatment: normal` |

## 11. Character economy per panel

- **≤ 4 characters per panel.** This is a HARD LIMIT (nanobanana stylesheet ref budget). 5 → split.
- For crowd scenes: 1 close-up of focal character + a wide establishing of the crowd, NOT both at once.
- When two characters talk: shot-reverse-shot is your friend (1 char per panel).

## 12. Color is the default — monochrome only for narrative reasons

Webtoon = full color by default. Modern readers expect color, the Webtoon platform standard is color, and emotional pacing comes from composition + pacing, not from lack of color.

**Set a monochrome `treatment` only when the narrative explicitly requires it.** In a typical chapter, ≥ 90% of panels are `treatment: normal` (color). Monochrome panels are rare beats — used like an italic in prose: emphasis, not the body voice.

### `treatment` options (per-panel override)

| Treatment | When to use | Look |
|---|---|---|
| `normal` | Default. ~90% of panels. | Full color, project style_description |
| `symbolic_dark` | Crisis / climax beat (≤ 3 / chapter). The monochrome here is *symbolic* — the world has narrowed to silhouette + shadow. | High-contrast B&W, heavy black, single accent light |
| `monochrome` | A deliberate monochrome panel inside a color chapter (rare; for stylistic punctuation). | Full B&W with screentone shading |
| `flashback_monochrome` | Memory / past-tense scene. Reader signal that this happened earlier. | Soft sepia, vintage paper, vignetted |
| `dream_desaturated` | Dream sequence, emotional dissociation. Color present but drained. | Heavy desaturation, ethereal glow |
| `imagined_surreal` | Character's imagination of something not real. | Color, but with ghostly translucent overlays |
| `photograph` | Diegetic photograph rendered inside the panel (the photo IS the subject). | Aged sepia paper texture |

### Rules for monochrome treatments
- **Use sparingly.** A chapter with > 5 monochrome panels usually means the story should have been a B&W work in the first place; reconsider whether the monochrome beats earn their place.
- **Cluster them when they happen.** If you need to show a flashback, do 2–4 consecutive `flashback_monochrome` panels, not one in the middle of color panels.
- **Bookend a flashback.** The panel BEFORE entering a flashback (color) and the one AFTER returning (color) should both have `distance_to_next_panel: jump` to signal scene/time change.
- **Climax `symbolic_dark`** typically has 1 panel only (the moment of breakdown), not a string of them.

## 13. Audio layer cues (bubbles.json)

### SFX (panel-level, fires at specific time)
- Each entry: `id, elevenlabs_prompt, duration_s ≤ 22, start_offset_s, volume_db`
- English prompt; specific about era/material ("wooden floorboards, traditional Japanese house", not just "footsteps")
- Foreground SFX volume_db: -8 to -3 dB; background SFX: -12 to -16 dB

### BGM (scene-level, ambient bed)
- Each entry: `scene_id, elevenlabs_prompt, volume_db (default -18), loop: true, fade_in_s, fade_out_s`
- Skip BGM for stark monologue-only scenes — silence has weight
- Use `bgm_cue: "fade_out"` on the last panel of a scene if the next scene has different BGM
- ElevenLabs SFX max 22 s/call → BGM is generated as a base ambience and looped

## 14. Aspect ratio choices

| Aspect | Use |
|---|---|
| `16:9` | Wide establishing shots, panoramic sweeps |
| `4:5` | Default for medium and close_up |
| `3:4` | Full-body character study |
| `2:1` | Extreme-close-up eyes (horizontal band) |
| `1:2` | Climax panels (tall, dominant) |

## 15. Quick adaptation checklist

When designing a chapter from prose, run through this in order:

1. **Beat decomposition**: read the chapter, mark every emotional / action beat (~6–10 beats per chapter)
2. **Scene grouping**: cluster beats by setting/time; one scene per setting
3. **Panel sketching per scene**: 3–5 panels typical; identify ONE shot type per panel
4. **Continuity check**: verify 180° axis and eye-line within each scene; jump between scenes
5. **Text overlay plan**: per panel, decide caption type & approx text. ≤ 4 bubbles/panel.
6. **In-image text & safe zones**: where will bubbles go? Mark the zones and any onomatopoeia.
7. **Audio layer**: per panel SFX (if anything happens), per scene BGM. Match SFX to in-image text via linked_sfx_id.
8. **Pacing pass**: too fast? add silent / aspect-to-aspect panels. Too slow? cut to action-to-action.
9. **Character count audit**: any panel > 4 characters? Split.
10. **Reading order audit**: bubbles flow right-top → left-bottom?

## 16. Common mistakes — avoid

- ❌ More than 4 characters in one panel
- ❌ Bubbles covering faces (didn't define safe zones)
- ❌ Long onomatopoeia (>4 chars) in in_image_text — nanobanana garbles
- ❌ Caption text in bubble form ("speech bubble dialogue" sent to nanobanana — image gen will try to draw text, fails)
- ❌ Eye-line jumps 180° between consecutive panels
- ❌ Same shot type 5 panels in a row (monotone — vary)
- ❌ Silent stretches > 6 panels with no narration (loses thread for monologue-heavy works)
- ❌ BGM that doesn't link across scene boundaries (abrupt cut — use fade cues)
- ❌ `extreme_close_up_eyes` more than twice per chapter (becomes a tic)
- ❌ Inventing dialogue not in source novel (review hit)
