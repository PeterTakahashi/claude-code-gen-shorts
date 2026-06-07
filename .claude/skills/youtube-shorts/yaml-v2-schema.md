# yaml v2 schema — language-neutral panels + per-language narration order

The v2 schema decouples **panels (visual assets)** from **narration (per-language scripts)**. Each narration line references a panel by id, so the panel order in the final video derives from the narration sequence — and that sequence can be **different for each language** (because Japanese vs English have different natural narrative flow).

## Why

Word-for-word translation often produces awkward word order. Example: an English sentence "His coworkers complained about his body odor every day" naturally lands a different beat than the Japanese equivalent. Each language deserves its own pacing and which-image-when choices, while sharing the same image library.

## Structure

```yaml
id: jobs-fruit-shower
parent_chapter: ch2

# Language-neutral panel library. id is referenced by `narration[].panel`.
panels:
  - id: night_shift_alone
    prompt: |
      9:16 vertical anime/webtoon illustration:
      A 19-year-old Steve Jobs alone at his Atari workbench at night...
      Character: {jobs_young}.
  - id: daytime_atari
    prompt: |
      A young 19-year-old Steve Jobs walking through a busy 1974 Atari office...
      Character: {jobs_young}.
  - id: fruit_diet
    prompt: |
      Close-up of Steve Jobs sitting cross-legged at his cluttered 1974 desk,
      holding a half-eaten apple...
  # ... 4-8 panels typical

# English script (primary — write this first).
en:
  title: "Why Steve Jobs Refused to Shower #Shorts"
  description: |
    The bizarre reason a young Steve Jobs refused to shower...
    #Shorts #SteveJobs #Apple #Biography
  hook_caption: "Why Steve Jobs Refused to Shower"
  series_brand: "Baltoon Biography"
  voice_speaker: "Ryan"             # Qwen3-TTS speaker (Ryan | Aiden)
  narration:
    - panel: night_shift_alone      # MUST reference an id from `panels`
      text: "His coworkers complained about his body odor so much, the company moved him to night shifts."
      caption: "Banished to the Night Shift"
    - panel: daytime_atari
      text: "That man was Steve Jobs, a 19-year-old engineer at Atari in 1974."
      caption: "1974, Atari, Age 19"
    - panel: fruit_diet
      text: "He rarely showered because he genuinely believed his fruit-only diet meant no body odor."
      caption: "His fruit-only diet"

# Japanese script (translated/adapted from English — order may differ).
ja:
  title: "ジョブズが風呂に入らなかった本当の理由 #Shorts"
  description: |
    天才スティーブ・ジョブズが、若い頃シャワーを浴びなかった本当の理由...
    #Shorts #スティーブジョブズ #Apple #人物伝
  hook_caption: "ジョブズが風呂に入らなかった理由"
  series_brand: "スティーブ・ジョブズ伝"
  voice_speed: 1.4                  # Aivis speed multiplier
  narration:
    - panel: night_shift_alone
      text: "同僚が、毎日、彼の体臭に苦情を訴え、夜勤に回された男がいます。"
      caption: "夜勤に飛ばされた天才"
    - panel: fruit_diet              # ← JA can pick this panel here even though EN had it later
      text: "果物だけ食べていれば体臭は出ない、と本気で信じていたから、シャワーを浴びなかったんです。"
      caption: "果物だけで体臭は出ない、と信じていた"
    - panel: daytime_atari           # ← order flexible per language
      text: "1974年、19歳のスティーブ・ジョブズ、Atari社のエンジニア時代の話です。"
      caption: "1974年、19歳、Atari社"
```

## Build flow

```bash
# 0. Author writes EN scenario first (or runs LLM authoring helper).

# 1. Translate EN → JA (LLM rewrites for natural JA flow, can reorder panel refs)
uv run python -m src.short_translate <project> --all --source-lang en --target-lang ja

# 2. Build EN video (panels generated once, shared across langs)
uv run python -m src.short_gen <project> --all --language en --batch

# 3. Build JA video (panels reuse cache from step 2)
uv run python -m src.short_gen <project> --all --language ja

# 4. Upload to per-language channels
.venv/bin/python -m src.youtube_batch_upload_shorts <project> --language en --channel baltoon_biography_en --privacy public
.venv/bin/python -m src.youtube_batch_upload_shorts <project> --language ja --channel ijinden_ja        --privacy public
```

## Backward compat

The old v1 schema (`narration` at top level, `i18n.en` for translations) is still supported:

- v1 detected when there's no `en:` / `ja:` / `panels[].id`
- v1 in `--language ja` build: top-level narration used, panels paired 1:1 with narration
- v1 in `--language en` build: `i18n.en.narration` paired 1:1 with panels (no reordering)

For new shorts, use v2. Old shorts work as-is.
