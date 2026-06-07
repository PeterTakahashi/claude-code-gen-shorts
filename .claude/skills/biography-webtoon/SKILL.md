---
name: biography-webtoon
description: Produce a multi-episode Japanese biography webtoon (anime-style first-person memoir) from research → series plan → scripts → panel images → TTS → MP4 → YouTube. Invoke when the user asks to "make a biography video", "create a webtoon about <person>", "build the next chapter", "再生成 (regenerate)", or "upload to YouTube". Series-aware (typically 12 episodes with K-drama cliffhangers + foreshadowing chains). Stack: Gemini 2.5 Flash Image (panels), Aivis TTS, ffmpeg, YouTube Data API.
---

# biography-webtoon — produce a 12-episode person biography series

Use this skill when working with the `webtoon-gen` repo to create or extend a **biographical** anime-style webtoon video series about a real person (e.g. Steve Jobs, Elon Musk). Each episode is ~4-6 min, first-person retrospective voice, ends on a K-drama cliffhanger that the next episode resolves in real time.

This is **distinct from `novel-to-webtoon`** which adapts an existing novel. Biography projects research the subject and write the script yourself (or with an agent subagent).

## Repo entrypoint scripts (use these — don't reinvent)

| Command | What it does |
|---|---|
| `uv run python -m src.init_biography <id> --subject <name> --title-ja <title>` | Bootstrap `projects/<id>/` skeleton |
| `uv run python -m src.plan_series <id>` | Gemini 2.5 Pro drafts a 12-episode arc + foreshadowing chains → `series_plan.yaml` |
| `uv run python -m src.arabize_bubbles <id> <ch1> [<ch2> …]` | Convert kanji numbers (五 → 5) in `bubbles.json` |
| `uv run python -m src.render_panels <id> <ch> --batch [--poll-interval=30]` | Submit a single Gemini batch for all panels in chapter (~25-60 min) |
| `uv run python -m src.render_panels <id> <ch> <scene_id>` | Re-render one scene (use for failed panels) |
| `uv run python -m src.narrate <id> <ch> [--force]` | Aivis TTS per panel → `audio/<pid>.mp3` + `_subtitles.json` |
| `uv run python -m src.audio_mixer <id> <ch> [--force]` | Mix voice + SFX → `chapter_master.wav` |
| `uv run python -m src.video_assembler <id> <ch> [--force]` | 1920×1080 still cuts + baked Japanese subtitles → `output/<ch>/master.mp4` |
| `uv run python -m src.thumbnail_gen <id> <ch> --series "シリーズ名"` | 1280×720 PNG thumbnail with episode number + title |
| **`uv run python -m src.build_chapter <id> <ch> [--series ...]`** | **All of the above in one go (idempotent)** |
| `uv run python -m src.build_series <id> --series "シリーズ名" [--from ch5]` | Loop build_chapter for every chapter in project.yaml |
| `uv run python -m src.youtube_batch_upload <id> [--privacy private]` | Upload every chapter listed in `upload_metadata.json`; resumable log under project dir |

## Mandatory writing rules (from user memory)

These are required for every biography project. They're enforced in the writing phase (when you produce `novel.txt` / `scenes.json` / `bubbles.json`).

### 1. Prose style — connective adult prose, NOT a list of past-tense sentences

**Why**: Strings of short past-tense sentences read like a child's report. This is for adults who want to understand motivation.

**Rule**: For every odd action, explain motivation with a conjunction (`Xだったので、Y`, `Xから、Y`, `Xと信じていたから、Y`). Pair behavior with consequence (`しかし`, `それでも`, `だから`, `結果として`). 1-3 sentences linked by conjunctions per bubble.

❌ `僕はシャワーを浴びなかった。同僚は苦情を言った。僕は夜勤に回された。`
✅ `僕は果物だけ食べていれば体臭は出ないと本気で信じていたから、シャワーを浴びなかった。同僚たちは毎日苦情を訴えたが、僕はそれを取り合わなかった。会社は最終的に、僕を夜勤に回すしかなかった。`

### 2. Time markers — always pair western year with relative time

**Why**: Viewers cannot judge elapsed time from a bare "1995年". Pair every year jump with a relative phrase.

**Rule**: First mention of a new year in a scene gets `「X年後の19YY年」`, `「翌1996年」`, `「それから半年後」`, etc. Include the subject's age occasionally (`「30歳になっていた」`).

### 3. Subtitle conventions (ch6+ onward)

- **People / places**: katakana (スティーブ, リード大学, ポートランド)
- **Companies / products**: English (Apple, iPhone, NeXT, Tesla, SpaceX)
- **Dates / numbers**: Arabic numerals (1976年, 25歳, 5,500人)

`arabize_bubbles` converts kanji numerals to Arabic — but it won't catch every case (e.g. 十分=enough vs 10分=10 min). Spot-check after running.

### 4. Reduce `、` (commas)

Don't split short modifier clauses with commas. Use them only at natural breath breaks. Never let 3+ `、` chain in one sentence.

❌ `彼は、不思議そうな、顔で、僕の旅費の、半分を、貸してくれた。`
✅ `彼は不思議そうな顔で、僕の旅費の半分を貸してくれた。`

### 5. Cliffhangers — K-drama frozen-fate per chapter

Every chapter ends on a frozen-moment cliffhanger that the next chapter resolves in real time. Don't compress: each cliffhanger must take ~3 panels (setup, peak, FADE TO BLACK ECU). The next chapter opens with the next moment of that frozen scene.

### 6. Length is flexible; content wins

Target ~4-6 min per episode (~25-30 panels) but never sacrifice a good beat for length. Cut filler instead of compressing climax.

## Image generation rules (from memory feedback)

These are baked into `scenes.json.background_style` for each panel:

- **No Japanese text inside images.** Decorative English-only or pure geometric shapes. Required for multi-language YouTube distribution.
- **Country / location must be explicit** in `background_style` (e.g. `1985 Cupertino California Apple corporate setting`, `clearly American suburban setting`). Without this, Gemini guesses Japanese settings.
- **Default outfit stays default** — don't inject scene-specific props into the character's default outfit string. Put scene props in `pose` or `background_style`.
- **Character continuity**: use Musk-/Jobs-like specific facial features in `description_en` (deep-set eyes, particular hair, build). Generic descriptions drift across panels.
- **Empty panels** (no characters): set `characters_in_panel: []` and add `no people visible` to `background_style`. Otherwise Gemini hallucinates random figures.
- **Anatomy negative**: project.yaml `style.negative` must include `extra fingers, extra limbs, distorted face, photorealistic, photograph, 3D render` to avoid common artifacts.

## End-to-end workflow

```
init_biography → plan_series (optional) →
  for each chapter:
    write novel.txt → scenes.json → bubbles.json →
    build_chapter (arabize + render + narrate + mix + assemble + thumbnail) →
  edit upload_metadata.json → youtube_batch_upload
```

### Phase 1 — Bootstrap project (1 command)

```bash
uv run python -m src.init_biography stevejobs \
  --subject "スティーブ・ジョブズ" --title-ja "スティーブ・ジョブズ伝" \
  --era "late 1950s through 2010s" --locale "Cupertino California Silicon Valley"
```

Then **edit** `projects/<id>/project.yaml` (chapters list, narrator voice) and `characters.yaml` (real cast with specific facial features). The bigger and more specific the face descriptions, the more consistent the panel images are across episodes.

### Phase 2 — Plan the 12-episode arc (optional but recommended)

```bash
uv run python -m src.plan_series stevejobs
```

This calls Gemini 2.5 Pro to draft a `series_plan.yaml` containing per-episode opening hook, key beats, climax, cliffhanger, and **foreshadowing chains** that pay off across multiple episodes (e.g. `abandoned_vs_chosen` planted ch1, paid off ch5).

Review the plan with the user before writing scripts — once cliffhangers are decided they cascade through every chapter.

### Phase 3 — Write a chapter (the creative core)

For each chapter, produce three files:

1. `work/chapters/<ch>/novel.txt` — first-person retrospective prose, 100-150 lines, connective style
2. `work/chapters/<ch>/scenes.json` — 10 scenes × ~3 panels = ~28-30 panels. Each panel needs:
   - `panel_id`, `shot_type`, `camera_angle`, `composition`, `aspect_ratio`, `intent` (Japanese description)
   - `characters_in_panel` (id + pose + direction)
   - `background_style` (English, explicit location, `no_japanese_text` flag)
   - `treatment`, `lighting`, `eye_line`, `emotion_primary`, `emotion_secondary`, `distance_to_next_panel`
3. `work/chapters/<ch>/bubbles.json` — text per panel, conjunction prose, speech in 「」

When the task is large, **delegate writing to a subagent per chapter** with explicit rules pasted in the prompt (see how `stevejobs ch5-ch12` was produced). Each agent reads ch1-ch4 as style reference plus `series_plan.yaml` and `characters.yaml`.

### Phase 4 — Build chapter to video (one command)

```bash
uv run python -m src.build_chapter stevejobs ch5 --series "スティーブ・ジョブズ伝"
```

This runs all six stages and skips ones whose output already exists. Use `--force` to regenerate everything.

If a Gemini batch returns `no image returned` for some panels (content policy or transient), inspect the log:

```bash
grep -E "no image|skipped" /tmp/sj_*_render.log
```

…and re-render just those scenes:

```bash
uv run python -m src.render_panels stevejobs ch7 scene_06
```

If a scene fails repeatedly, edit the panel's `background_style` and `intent` in `scenes.json` to remove copyrighted-character references (e.g. specific Toy Story / movie IP imagery), generalize to abstract shapes, and retry.

### Phase 5 — Build entire series

```bash
uv run python -m src.build_series stevejobs --series "スティーブ・ジョブズ伝"
```

Or to start from a specific chapter:

```bash
uv run python -m src.build_series stevejobs --series "..." --from ch5
```

### Phase 6 — YouTube upload

Edit `projects/<id>/upload_metadata.json` (created by init_biography). For each chapter add:

```json
{
  "id": "ch1",
  "title": "【シリーズ名】第1話 サブタイトル",
  "description": "3-5行の章サマリー"
}
```

The footer (`common_description_footer`) is appended automatically. Then:

```bash
PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_batch_upload stevejobs --privacy private
```

The script writes `.youtube_uploads.json` next to upload_metadata.json. Already-uploaded chapters get skipped on re-runs (use `--force` to re-upload).

First run opens a browser for OAuth (loopback `localhost:8080`). The cached token at `.youtube_token.json` is reused on subsequent runs.

## Parallelism notes

- **Gemini batches** can run in parallel — 8 simultaneous batches worked fine for stevejobs ch5-ch12. Each takes 25-60 min. Submit all then sleep / wakeup.
- **Audio/video pipeline** is CPU-bound but cheap — sequential per chapter is OK.
- **YouTube upload** is rate-limited; sequential is correct.

## Cost ballpark (one 12-episode series)

- Panels: 12 × 30 × $0.039 = **~$14** with Gemini batch 50%-off
- TTS: free (local Aivis)
- Series plan + agent writing: a few dollars in Gemini Pro / Claude tokens
- YouTube: free

## Recovery / common issues

| Symptom | Fix |
|---|---|
| Some panels missing after batch SUCCEEDED | `grep "no image" /tmp/*_render.log`, re-render the scene |
| Same panel keeps failing | Edit `scenes.json` to remove copyright-likely content (specific movie/character imagery), generalize |
| Token error on upload | Delete `.youtube_token.json`, re-auth; OAuth client must allow `localhost:8080` redirect |
| Audio mid-sentence tone jumps | TTS chunking should split only at `。！？` — check `src/subtitle_split.py:split_for_tts` not splitting at `、` |
| Image inside-image text shows Japanese | `background_style` must include `no japanese text` / `no_text_visible`; rerun |

## Related skills / docs

- `webtoon-scenario-design` — visual-narrative design rules for scenes.json authoring
- User memory at `~/.claude/projects/-Users-apple-dev-claude-code-webtoon-gen/memory/MEMORY.md` — feedback rules (prose style, time markers, image consistency, OAuth buffering)
