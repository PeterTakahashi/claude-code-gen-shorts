---
name: youtube-shorts
description: Produce 9:16 vertical YouTube Shorts that are **self-contained, satisfying micro-stories**. Use when the user asks to "make a short", "create a shorts video", "shortsを作って". Specialized for the "static image + TTS narration" composition style used in webtoon-gen. Encodes 2026 best practices: 3-sec hook, 20-45 sec total, hard captions, 9:16, COMPLETE story arc (setup → climax → resolution) within the short itself. The short IS the content — not a promo for long-form. Subtle channel branding only. Trending music CANNOT be added via API; falls back to royalty-free or noted as manual YouTube Studio step.
---

# youtube-shorts — produce self-contained 9:16 micro-stories

Use this skill when working with the `webtoon-gen` repo to create short-form vertical videos. **Critical mindset**: Shorts viewers swipe through their feed casually. They have no interest in watching a "promo for a long video". The short must be **entertaining and complete on its own merit** — a satisfying mini-story they're glad they watched. Long-form discovery happens as a bonus when they search the channel later, not because the short teases them.

**Wrong framing** (don't do this): "Here's a teaser of episode 5, watch the full 6-minute video on our channel!"
**Right framing**: "Here's a complete 30-second story about Jobs not bathing — funny, surprising, with a satisfying punchline." If the viewer is hooked by the subject, they'll click the channel name themselves.

## What a successful short looks like (2026 best practices)

| Element | Spec | Why |
|---|---|---|
| Aspect ratio | **9:16 (1080×1920)** | YouTube Shorts requirement; non-vertical demoted by algorithm |
| Length | **20-45 sec** (sweet spot 25-30) | Under 15s lacks depth; over 45s drops completion rate |
| Hook | **The climax/punchline in first 2-3 sec** | The shock image is what stops the swipe |
| Captions | **Big, hard-burned** | 85% watch with sound off; captions ARE the hook delivery |
| Visual pace | **Static images, beat-cut every 3-4 sec — panel count scales with length** | No zoompan; but a single image held >4s reads as "static slideshow" and gets swiped. Panel count ≈ total_sec ÷ 3.5 (e.g. 58s → ~16 panels, NOT 6) |
| Opening cut | **First image switches at ~1.5s** | A 5-7s held first image = instant "this is just a slideshow" swipe. `short_gen.py` enforces this via `opening_cut` (default 1.5s); also author the first narration beat as a short 1-2s punch line |
| Audio | TTS narration at ~1.4× speed | Punchy pace appropriate for Shorts |
| Title/desc | Includes **`#Shorts`** | Tells YouTube it's a short |
| Story arc | **Payoff at start → backstory → return to payoff (loop)** | Loop-friendly: ending matches beginning |
| End card | **NONE** | A clear end signals "swipe away". Skip it. The first frame is the loop point. |

## The biography-shorts content pattern — Cold Open / Loop-Friendly

Every short opens with the **climax image and a payoff caption**, then unwinds the backstory, then returns to that same climax frame. YouTube Shorts auto-loops the video, so the start image == the end image == seamless loop point. There is **no explicit end card**.

### Structure (25-35 sec total)

```
[0-1.5s] Climax image  (the "WTF/why" moment) — SHORT first beat
         First narration beat is a 1-2s punch line, image cuts fast
         Bottom caption: punchline ("夜勤に飛ばされた天才")

[1.5-25s] Backstory cuts — one panel per ~3-4s of narration, static
         Bottom captions sync to TTS narration
         Tell the "how we got here"

[~end]   Return to the climax image / continuation of climax
         Narration arrives at the same moment we opened on
         No end card — last frame loops back to frame 1
```

**Image density rule (critical for retention):** target **3-4 seconds per panel for the WHOLE video**, not just the opening. Panel count scales with length: `panels ≈ total_sec ÷ 3.5`. A 30s short → ~9 panels; a 58s short → ~16 panels. Do NOT write 2-3 sentences per panel (that yields 9-10s static holds). Split narration into short beats — roughly **one short sentence per panel** — and give each beat its own image. (EN narration is already beat-sized; JA narration tends to run long — split it.)

### Templates

1. **"何これ? → なるほど → そして繋がる"**
   - Open: 同僚が鼻を覆っている画像 + "夜勤に飛ばされた天才"
   - Body: 1974年、ジョブズは果物だけで体臭は出ないと信じていた...
   - Loop: 同じ画像に戻り narration が結末を述べる

2. **"伝説の一言を冒頭に → 経緯 → そして"**
   - Open: スカリー頷きの画像 + "2年後、ジョブズを追放する男"
   - Body: 1983年、ジョブズの口説き文句で彼は頷いたが...
   - Loop: 同じ画像に戻り「皮肉な結末」を narration が締める

3. **"勝利の瞬間を先に → 苦難の物語 → そして勝利"**
   - Open: ロケット成功画像 + "民間初の軌道到達"
   - Body: 3回連続爆発、銀行残高は底...
   - Loop: 4機目成功画像に戻り「世界初の瞬間」と narration

### Hook caption (top, persistent)

The top caption stays nearly constant. It's the **reason to keep watching**:
- 「ジョブズが風呂に入らなかった理由」 — promises an explanation
- 「Twitter を 440億ドルで買った男」 — promises a story
- 「3回連続爆発、4回目で起きたこと」 — promises a resolution

Below it, a smaller `series_brand` line ("スティーブ・ジョブズ伝") tells viewers this is one of many similar shorts.

## Audio strategy (the trending-music problem)

YouTube Data API v3 does **not** support attaching trending sounds when uploading. The Shorts trending audio library is only accessible via the YouTube app's Shorts editor.

**Choices, in order of effort:**

1. **TTS narration only** (current default — works fine for biography)
2. **TTS + royalty-free ambient bed** (mix at -22 LUFS for music, -16 for voice)
   - YouTube Audio Library: https://studio.youtube.com/channel/UC.../music
   - Pixabay, Freesound, Incompetech (CC-BY)
3. **Upload silent, then add trending sound manually in YouTube Studio Shorts editor** (best engagement)
   - This is the only path to trending sounds. Worth doing for your top 1-2 shorts of the week.

The `short_gen.py` script supports all three modes via `--bgm <path>` or `--silent` flags.

## Repo entrypoints

| Command | What it does |
|---|---|
| `uv run python -m src.short_gen <project_id> <short_id>` | Build one short from `projects/<id>/shorts/<short_id>.yaml` config |
| `uv run python -m src.short_gen <project_id> --all` | Build every short config under `projects/<id>/shorts/` |
| `uv run python -m src.short_gen <project_id> --all --batch` | **Recommended for multi-short runs**: pre-generate all panel images via Gemini Batch API (50% off, 20-60min wait) |
| `uv run python -m src.short_gen <project_id> <short_id> --language en` | **Build the English variant** (uses i18n.en.* from yaml + Qwen3-TTS speaker Ryan). Output: `output/shorts/<sid>/en/short.mp4` |
| `uv run python -m src.short_translate <project_id> --all` | LLM-translate JA shorts → adds `i18n.en` section to each yaml |
| `uv run python -m src.youtube_batch_upload_shorts <project_id>` | Upload all shorts (JA, default) |
| `uv run python -m src.youtube_batch_upload_shorts <project_id> --channel baltoon_biography_en --language en` | Upload English variants to the English channel |

## Short config schema (`projects/<id>/shorts/<short_id>.yaml`)

```yaml
id: stevejobs-ch2-fruit
parent_chapter: ch2          # the long-form chapter this short funnels to
title: "ジョブズが風呂に入らなかった本当の理由 #Shorts"
description: |
  天才スティーブ・ジョブズが風呂に入らなかった本当の理由とは。
  続きはチャンネルの『スティーブ・ジョブズ伝』で。
  #Shorts #スティーブジョブズ #Apple

hook_caption: "ジョブズが風呂に入らなかった理由"     # big text on first frame, 2 sec
cta_caption: "続きはチャンネルで"                  # last 3 sec
cta_url_hint: ""                                  # optional second line on CTA card

# Panels in order. Each is 2-6 sec with Ken Burns zoom/pan.
# Source can be:
#   reuse: <project>/<chapter>/<scene_id>/<pid>_best.png  (crop+pad to 9:16)
#   regenerate: a fresh Gemini vertical render with this prompt
panels:
  - source: reuse:ch2/scene_05/scene_05_p01
    duration: 4
    pan: zoom_in
    caption: "1974年、Atari社"
  - source: reuse:ch2/scene_05/scene_05_p02
    duration: 6
    pan: zoom_out
    caption: "果物だけ食べていれば体臭は出ないと信じていた"

# Narration script (TTS'd with the project narrator voice).
# Targets 25-35 sec total when read at narrator voice_speed.
narration: |
  1974年、19歳のスティーブ・ジョブズが、Atari 社で働いていた頃の話です。
  彼は、果物だけ食べていれば体臭は出ないと、本気で信じていたから、
  シャワーを浴びませんでした。
  当然、同僚たちは毎日苦情を訴えました。
  会社は最終的に、彼を夜勤に回すしかなかった——
  天才の奇行は、若い頃からだったんです。

# Optional background music
bgm: null                  # path to bg track; null = no music
bgm_db: -22                # mix level (LUFS-ish)
```

## Composition pipeline

`short_gen.py` does:

1. **Read the YAML config.**
2. **Resolve panels.**
   - `reuse:` → open existing 16:9 png, fit-vertical via blurred-bg pad (so nothing is cropped out), resize to 1080×1920
   - `regenerate:` → submit a single-image Gemini request with `aspect_ratio: 9:16` and the prompt; cache under `output/shorts/<short_id>/panels/`
3. **Generate narration TTS** via Aivis (reuses project narrator config).
4. **Compose video** with FFmpeg:
   - Each panel runs for its `duration` with `zoompan` filter (slow zoom in/out/pan)
   - Hook caption (3 sec): big bold text overlay on first panel
   - Per-panel captions: secondary text overlay
   - CTA card: 3-5 sec, white background with playlist URL text
   - Audio: narration mp3 (looped silence padded to video length); optional bgm side-chained at low level
   - Output: H.264 mp4 at 1080×1920, 30fps, +faststart for fast playback
5. **Write metadata** (title, description with #Shorts, parent_video_id) to DB → `videos.kind='short'`, `parent_video_id=<chapter long-form video_id>`

## Vertical panel rendering

For panels marked `regenerate:`, the script passes `--aspect-ratio 9:16` to Gemini's image API. The character + scene description is the same as the long-form panel; only aspect ratio changes. This is **the best quality** approach for the hook frame.

For `reuse:` (the default), we crop and pad:
- The original 16:9 panel is the **center band** of the 9:16 canvas (not stretched)
- The top and bottom strips are filled with a Gaussian-blurred copy of the same panel (the "fake bokeh" look familiar on TikTok / Reels)
- Critical content (face, key prop) stays in the center band

## Captions

Big and bold. We use NotoSansJP-Bold at ~96pt for hook captions (occupy bottom 35% of frame), 60pt for per-panel captions, ~80pt for the CTA card. White text with thick black stroke for legibility on any background. Lines wrap automatically.

## Cost ballpark

Per short:
- 0-2 Gemini regenerate panel images: $0-0.10
- TTS narration: free (local Aivis)
- Compose: free (local FFmpeg)
- Upload: free (YouTube API quota)

Per series of 6 shorts: **< $1 in API costs**.

## Upload + DB

`src/youtube_batch_upload_shorts.py` reads `projects/<id>/shorts/*.yaml`, uploads each as a private (or public) YouTube video with `#Shorts` in title, then writes to DB:

- `videos.kind = 'short'`
- `videos.parent_video_id = <long-form chapter's video_id>`
- `videos.tags` includes `Shorts`

Stats sync (`src/youtube_stats_sync.py`) tracks both long and short in the same `video_stats` table, so you can later query "which shorts drive the most clicks to the long-form".

## Recommended cadence

- **Per chapter**: 1 short tied to the most dramatic beat (the cliffhanger or the most surprising fact)
- **Per week**: post 3-5 shorts (daily-ish) to feed the Shorts algorithm
- **Title formula**: `「[curiosity-gap hook] #Shorts」` (Japanese hook should be the first 12 chars to fit in feed previews)

## Common pitfalls

| Pitfall | Fix |
|---|---|
| Static panel for 30 sec → no completion | Add visible zoompan motion + caption changes |
| Subtitle text too small / too long | One short line (max 18 chars), 60-96pt |
| Audio plays but no caption → mute viewers bounce | Bake captions into the video frame, not as YouTube CC |
| Trending sound missing | This is API-locked; accept it or add manually post-upload |
| Aspect ratio wrong (16:9 letterboxed) | Final mp4 MUST be 1080×1920 — verify with ffprobe |
| Long-form description with full chapter summary in short | Short description = hook + #Shorts + playlist link only |

## Sources

This skill synthesizes 2026 best practices from:
- [Miraflow — YouTube Shorts Best Practices 2026](https://miraflow.ai/blog/youtube-shorts-best-practices-2026-complete-guide)
- [JoinBrands — YouTube Shorts (2026): 10 Tips](https://joinbrands.com/blog/youtube-shorts-best-practices/)
- [Klap.app — 10 Best Practices to Go Viral 2025](https://klap.app/blog/youtube-shorts-best-practices)
- FFmpeg [zoompan](https://ffmpeg.org/ffmpeg-filters.html#zoompan) docs
- API trending music constraint confirmed via Ayrshare + Phyllo docs

Plus user memory:
- biography-webtoon workflow (parent skill)
- 画像内日本語禁止 (no Japanese in image text, but captions burned outside images are fine)
- 西暦には相対時間を併記 (apply to narration here too)
