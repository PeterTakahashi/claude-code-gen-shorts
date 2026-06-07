---
name: novel-to-webtoon
description: Run the local webtoon-gen pipeline that turns a novel into a vertical-scroll webtoon video (PNG + narrated MP4). Invoke when the user asks to "generate a webtoon from a novel", "run the pipeline", "regenerate panels/voice/audio", or troubleshoot a stage. Stack: Gemini nanobanana (image), Aivis local TTS, ElevenLabs SFX/BGM, Claude (scenario LLM), Codex (review), Whisper (voice verify), ffmpeg (video). Knows the project layout, idempotent stage map S0–S22, four mandatory human checkpoints, and recovery workflows.
---

# novel-to-webtoon — pipeline runner

Use this skill when working with the `webtoon-gen` repo at the user's machine. It produces vertical-scroll webtoon PNGs and narrated MP4 videos from prose novels.

## Stack at a glance

| Layer | Tool |
|---|---|
| Visual scenario LLM | Claude Code (`claude -p`) |
| Scenario QA | Codex (`codex exec`) — optional |
| Image gen | Gemini 2.5 Flash Image (nanobanana) via `GEMINI_API_KEY` |
| TTS | Aivis (VOICEVOX-compatible) at `http://127.0.0.1:10101` |
| SFX / BGM | ElevenLabs `/v1/sound-generation` via `ELEVEN_LABS_API_KEY` |
| Voice verification | openai-whisper (large-v3) + pykakasi + rapidfuzz |
| Video / audio | ffmpeg (H.264 + AAC, sidechain ducking) |

Read the **`webtoon-scenario-design`** skill for the visual-narrative rules that scene/bubble authoring must follow. This skill (novel-to-webtoon) covers the *how to operate* side.

## Project layout

```
webtoon-gen/
├── projects/<novel_id>/
│   ├── project.yaml          # title, era, style, chapter markers, narrator, voice config, output_targets
│   ├── characters.yaml       # roster + voice_style_id + selected_candidate
│   ├── lexicon.yaml          # kanji → reading overrides (M5)
│   ├── input/novel.txt       # source text
│   ├── characters/<id>/      # candidates/, selected.png, stylesheet_*.png
│   ├── work/chapters/<ch>/
│   │   ├── novel.txt              # extracted chapter
│   │   ├── scenes.json            # visual layer (with in_image_text, bubble_safe_zones)
│   │   ├── bubbles.json           # text + sfx + scene_bgm
│   │   ├── panels/<scene>/<pid>_best.png
│   │   ├── bubbled/<scene>/<pid>_bubbled.png
│   │   ├── audio/<pid>.mp3            # voice (Aivis)
│   │   ├── audio/sfx/<pid>_<n>.mp3    # ElevenLabs
│   │   ├── audio/bgm/<scene>.wav      # ElevenLabs ambience (looped)
│   │   ├── audio/mix/<pid>.wav        # voice + sfx
│   │   ├── audio/mix/chapter_master.wav # final 3-track mix
│   │   ├── pages/<pid>.png            # 1080×1920 page frames
│   │   ├── video_segs/                # hold/transition mp4 clips
│   │   ├── panel_positions.json
│   │   ├── voice_review.md            # Whisper-flagged readings (M5 layer 3)
│   │   ├── reviews/round_<N>.md       # Codex scenario reviews (M6)
│   │   └── webtoon_for_video.png
│   └── output/<ch>/
│       ├── webtoon.png                # vertical scroll PNG (the comic)
│       ├── webtoon_scroll.mp4         # 1080×1920 master video with audio
│       ├── tiktok_shorts.mp4          # 9:16 ≤ 60s (M8)
│       ├── youtube_long.mp4           # 16:9 full chapter (M8)
│       └── webtoon_static.png         # copy of webtoon.png for static-distribution targets
└── prompts/                  # claude -p / codex exec templates
```

## Single-command entry

```bash
uv run python -m src.pipeline <novel_id> [--chapter <ch>] [--force]
```

The pipeline runs **idempotent** stages until the next human-review checkpoint, then exits with instructions. Re-running picks up where it left off.

## Stage map (run order)

| # | Stage | Auto / LLM / CHK | Output |
|---|---|---|---|
| S0 | validate inputs | auto | — |
| S1 | split novel by chapter markers | auto | `work/chapters/<ch>/novel.txt` |
| S2 | extract characters.yaml (`claude -p` extract_characters.md) | LLM | `characters.yaml` → **CHK review** |
| S2.5 | verify Aivis voice models installed | auto | (validation only) |
| S3 | generate 4 character candidates per "designed" character (Gemini) | auto | `characters/<id>/candidates/*.png` |
| S4 | select character candidate | **CHK** | `selected.png` |
| S5 | generate stylesheets (turnaround + expressions) | auto | `stylesheet_*.png` |
| S6 | decompose scenes (`claude -p` decompose_scenes.md → uses scenario-design skill) | LLM | `scenes.json` → **CHK review** |
| S7 | render panels (Gemini, refs = stylesheet + prev panel) | auto | `panels/<scene>/<pid>_best.png` |
| S8 | author bubbles (`claude -p` author_bubbles.md, **vision** — sees rendered panels) | LLM | `bubbles.json` → **CHK review** |
| S9 | compose webtoon PNG (PIL bubble overlay → vertical stitch) | auto | `webtoon.png` + `panel_positions.json` |
| S10 | narrate audio (Aivis 3-layer: lexicon → audio_query → wav) | auto | `audio/<pid>.mp3` |
| S10b | voice verify (Whisper large-v3 + Levenshtein) | auto / **CHK if flagged** | `voice_review.md` |
| S10c | SFX (ElevenLabs) | auto | `audio/sfx/*.mp3` |
| S10d | BGM (ElevenLabs ambience + ffmpeg loop+fade) | auto | `audio/bgm/*.wav` |
| S11 | scroll video (hold-then-scroll) | auto | `webtoon_scroll.mp4` |
| S12 | audio mix master + overlay onto video | auto | `chapter_master.wav` overlaid |
| S13 | per-target encoding (output_targets[]) | auto | `tiktok_shorts.mp4` etc. |

## The four mandatory human checkpoints (Tier 1)

These cannot be skipped without quality loss. Each takes < 10 minutes:

1. **S2 characters.yaml**: confirm cast + which characters need design (`expressions:` field present)
2. **S3 lexicon.yaml** (recommended): pre-populate kanji readings before voice generation
3. **S4 candidate selection**: pick 1 of 4 candidates per designed character; set `selected_candidate: <N>` in characters.yaml or `cp candidates/N.png selected.png`
4. **S7 stylesheet visual**: open the generated turnaround + expression PNG; if drift (4 poses look different), discard and re-pick a candidate

Tier 2 (Codex auto-review + human spot-check): S6 scenes.json, S8 bubbles.json, S10b voice_review.md
Tier 3 (essential final QA): watch the assembled webtoon_scroll.mp4 end-to-end

See PIPELINE.md §12 for the full review policy.

## Adding a new novel

```bash
cp -r projects/_template projects/<novel_id>
cd projects/<novel_id>
mv project.yaml.example project.yaml
$EDITOR project.yaml          # title, era, style, chapter markers, narrator
cp /path/to/novel.txt input/novel.txt

uv run python -m src.pipeline <novel_id>
# → pauses at S2; review characters.yaml; re-run
# → pauses at S4; pick candidates; re-run
# → pauses at S6 with auto-generated scenes.json; review; re-run
# → ...
```

## Common workflows

### Regenerate one panel image
```bash
rm projects/<id>/work/chapters/<ch>/panels/<scene>/<pid>_best.png
uv run python -m src.render_panels <id> <ch>      # only the missing panel re-renders
```

### Re-narrate after a lexicon edit
```bash
$EDITOR projects/<id>/lexicon.yaml                 # add { surface: 葉蔵, reading: ようぞう, kind: name }
# Force-regen only the panels whose text contains the new surface:
python3 -c "
import json
b = json.load(open('projects/<id>/work/chapters/<ch>/bubbles.json'))
for p in b['panels']:
    if any('葉蔵' in bub.get('text','') for bub in p['bubbles']):
        print(p['panel_id'])
" | xargs -I {} rm projects/<id>/work/chapters/<ch>/audio/{}.mp3
uv run python -m src.narrate <id> <ch>
uv run python -m src.audio_mixer <id> <ch> --force   # rebuild master + overlay
```

### Re-mix audio after BGM volume tweak
```bash
$EDITOR projects/<id>/work/chapters/<ch>/bubbles.json   # change scene_bgm[0].volume_db
rm projects/<id>/work/chapters/<ch>/audio/bgm/<scene>.wav
uv run python -m src.synth_bgm <id> <ch>            # regen affected BGM
uv run python -m src.audio_mixer <id> <ch> --force  # rebuild master
```

### Bubble position adjustment (no API call needed)
```bash
$EDITOR projects/<id>/work/chapters/<ch>/bubbles.json   # change panels[].bubbles[].x_pct/y_pct
uv run python -m src.compose_webtoon <id> <ch> --force  # re-render PIL bubbles + restitch
uv run python -m src.scroll_video <id> <ch> --force     # rebuild video
uv run python -m src.audio_mixer <id> <ch> --force      # re-overlay master audio
```

### Run Whisper verify on demand
```bash
uv run python -m src.voice_verify <id> <ch> --force [--model=large-v3|small]
# → writes voice_review.md with similarity < threshold panels + suggested lexicon entries
```

### Run Codex scenario review
First enable in project.yaml:
```yaml
review:
  codex_enabled: true
```
Then:
```bash
uv run python -m src.codex_review <id> <ch>
# → writes work/chapters/<ch>/reviews/round_<N>.md
```

### Critic rubric across panels (M7)
```bash
uv run python -m src.critic <id> <ch>
# → writes critiques.json with per-panel score (out of 80) + retry hints for low scores
```

### Encode to a single output target
```bash
uv run python -m src.encode_targets <id> <ch>          # all targets in project.yaml
```

## Recovery — when something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `claude -p did not write <path>` | Claude finished but didn't use Write tool | Re-run; or open Claude Code interactively and run the prompt by hand |
| `MISSING N voice style(s)` at S2.5 | Aivis model not installed | Open Aivis app or `POST /aivm_models/install` |
| Same character looks like a different person across panels | Stylesheet drift or stylesheets regenerated mid-chapter | Restore old stylesheet from git; `--force` on render_panels for affected panels only |
| Audio out of sync with video by < 100 ms | New voice durations don't match old video timeline | `rm output/<ch>/webtoon_scroll.mp4` and `rm -rf work/.../video_segs/* pages/*`; re-run scroll_video and audio_mixer |
| Whisper finds 5 + readings wrong | Lexicon under-populated | Merge `voice_review.md` suggestions into `lexicon.yaml`; force-regen affected voices |
| nanobanana drew speech bubbles inside the panel | `negative` prompt too narrow | Confirm `bubble_safe_zones[]` is set; ensure render_panels.compose_prompt adds `speech bubbles, dialogue captions` to negative |
| ElevenLabs SFX too short for BGM | SFX API caps at 22 s | synth_bgm already loops with ffmpeg; check `extra_tail_s` and scene_voice_total in computation |

## Cost & time estimates (per chapter, ~40 panels)

| Stage | Time | Cost (approx) |
|---|---|---|
| nanobanana panels (40 × 1) | ~5 min | $1.6 |
| nanobanana candidates (6 char × 4) | ~3 min | $0.94 |
| nanobanana stylesheets (6 × 2) | ~2 min | $0.47 |
| Aivis TTS | local, 6–10 min | free |
| ElevenLabs SFX (~10 calls) | 1 min | $0.30 |
| ElevenLabs BGM (~6 scenes × 1 base) | 1 min | $0.20 |
| Whisper verify (large-v3, 12 min audio) | 10–15 min | free |
| Audio mix + video build | 2–3 min | free |
| Per-target encoding (3 targets) | 2 min | free |
| **Total per chapter** | ~30–45 min | **~$3.5** |

Re-running any stage's --force only costs the redone stage.

## Configuration cheat sheet

### project.yaml minimum fields
```yaml
id: <novel_id>
title_ja: …
title_en: …
language: ja
era: "early Showa era Japan, 1920s-1930s"
style:
  description: "monochrome black-and-white webtoon manga, …"
  negative: "speech bubbles, dialogue captions, watermark, color"
chapters:
  - { id: chapter_01, title: 第一の手記, start_marker: 第一の手記, end_marker: 第二の手記 }
narrator:
  voice_style_id: 1310138977   # Aivis style id
  voice_speed: 0.95
voice:
  engine: aivis
  endpoint: "http://127.0.0.1:10101"
  verify: true
  similarity_threshold: 0.88
  whisper: { model: large-v3 }
bubbles:
  font_path: "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
  font_index: 0
  font_scale: 1.5
webtoon:
  width_px: 800
  panel_gap_px: { tight: 20, breath: 80, jump: 200 }
output_targets:
  - { name: tiktok_shorts, kind: video, aspect: "9:16", max_duration_s: 60 }
  - { name: youtube_long,  kind: video, aspect: "16:9" }
  - { name: webtoon_static, kind: static }
review:
  codex_enabled: false
```

### characters.yaml entry
```yaml
- id: yozo_child
  name_ja: 大庭葉蔵（幼少）
  description_en: "<English physical description, no plot/personality>"
  outfit_en: "<era-appropriate clothing>"
  voice_style_id: 1310138977
  voice_speed: 0.95
  voice_instructions: null      # optional, falls back to narrator
  selected_candidate: 2         # set after S4 selection (1..4)
  expressions:                  # presence of this field = "needs visual design" (S3-S5 will run)
    - neutral blank
    - performative smile
    - …
  poses:                        # optional 4-pose turnaround override
    - "Front view, arms relaxed at sides"
    - "Three-quarter view facing camera left at 45°"
    - "Pure side profile facing camera left"
    - "Back view from behind"
```

A character without `expressions` is **description-only**: it appears in panel prompts via `description_en` injection but doesn't get candidates / stylesheet / S4 checkpoint. Use this for minor named characters.

## When the user says…

| User intent | What to run |
|---|---|
| "Start a new novel" | Copy `_template`; edit project.yaml; place novel.txt; run pipeline |
| "Run the pipeline" | `uv run python -m src.pipeline <id>` |
| "Continue past a checkpoint" | After they edit the flagged file, re-run the pipeline (same command) |
| "Regenerate panel X" | `rm <pid>_best.png && python -m src.render_panels <id> <ch>` |
| "Re-narrate everything" | `python -m src.narrate <id> <ch> --force` then `python -m src.audio_mixer <id> <ch> --force` |
| "Make a 9:16 short" | Already in output_targets — `python -m src.encode_targets <id> <ch>` |
| "Why does the protagonist say 'はくら' instead of 'ようぞう'?" | Add `{ surface: 葉蔵, reading: ようぞう, kind: name }` to lexicon.yaml; force-regen affected voices; rebuild master |
| "Verify all readings are correct" | `python -m src.voice_verify <id> <ch>` then read voice_review.md |
| "Review the scenario quality" | Enable `review.codex_enabled: true` in project.yaml; run `python -m src.codex_review <id> <ch>` |

## When in doubt

1. Check `PIPELINE.md` for the canonical specification (this skill is a runtime companion to that doc).
2. Check `SPEC.md` for the original 人間失格-specific design notes (legacy reference).
3. The `webtoon-scenario-design` skill is the **mandatory reference** for any scene/bubble LLM authoring.
