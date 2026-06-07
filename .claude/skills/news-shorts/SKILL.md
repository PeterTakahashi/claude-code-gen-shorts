---
name: news-shorts
description: Produce 9:16 vertical YouTube Shorts in **news-broadcast style** (HeyGen anchor opener, MM/dd date badge, faster pacing, more panel cuts) for the 5 news verticals — stocks_news / crypto_news / tech_news / politics_news / world_news. Use when the user asks to "create a news short", "ニュースショートを作って", or wants topical breaking-news shorts. Encodes 2026 best practices: 1.25× speed narration (pitch −0.10), 12+ panels for 40 sec, today's date badge top-right, HeyGen photo-avatar talking-head opener (5 sec) with title + per-segment subtitle composited on. Source-grounded narration from Nikkei / Bloomberg via `news_fetch.py`; per-panel Bing reference images via `news_image_ref.py` (copyright-safe redraw by nanobanana).
---

# news-shorts — produce 9:16 news-broadcast shorts

Use this skill when working with the `webtoon-gen` repo to create **news shorts** that feel like a broadcast clip rather than a slideshow. The 5 target channels are `baltoon_stocks_news_ja`, `baltoon_crypto_news_ja`, `baltoon_tech_news_ja`, `baltoon_politics_news_ja`, `baltoon_world_news_ja` (registered in DB, OAuth tokens at `.youtube_token.<channel>.json`).

## What separates news shorts from regular [[youtube-shorts]]

| Element | Spec | Why |
|---|---|---|
| **Voice** | 凛音エル / ノーマル, `voice_speed: 1.25`, `voice_pitch: -0.10` | News-anchor pace with a touch more authority. 1.5× was too rushed; 1.25× with slightly lower pitch reads as composed broadcast voice. Set as project default in `projects/news_test_1/project.yaml`; override per-short via `ja.voice_speed` / `ja.voice_pitch`. |
| **Panel count** | **≥12 panels per 40 sec short** (≈3-4 sec each) | Author one narration beat per panel. Each beat ≤ 40 Japanese characters → ~3 sec audio. |
| **Top-right date** | `date_overlay: auto` → today's `MM/dd` (red badge, vertically centered) | Standard news-broadcast affordance. `auto` resolves to today; explicit string also works (`"05/29"`). |
| **Talking-head opener** | First **5 sec** via **HeyGen** photo-avatar (`tools/sync_anchor_opener.py --backend heygen`) | Sync.so/Sync.so react-1 produced no visible mouth motion from a still image; HeyGen avatars (pre-created via the HeyGen Web app) lipsync the Aivis audio reliably. **Critical**: the user-facing "avatar id" in the HeyGen UI is a `group_id`; the actual `avatar_id` to pass to `/v3/videos` is the **look id** from `GET /v3/avatars/looks?ownership=private`. |
| **Opener captions** | Hook + per-segment subtitle + date badge are composited onto the HeyGen output via `apply_captions_to_opener` (ffmpeg `overlay` filter, switched per segment using cached `seg_NN.mp3` durations) | Keeps visual parity with the rest of the short (which bakes captions per panel via PIL). |
| **Date freshness** | Topic ≤ 48 hours old | News shorts MUST be recent. Source from [[news_fetch.py]] on Nikkei/Bloomberg, or X via `x_trending.py` for high-engagement headlines. |
| **Series brand** | Topic-specific, NOT channel name (e.g., "スクエニ急落の理由") | See [[feedback_short_series_brand_topic_specific]] — channel name in subtitle is dead weight. |
| **Style** | `image_style: photorealistic` for credibility | News-broadcast aesthetic. anime is acceptable for entertainment-business stories but photoreal is the default. |
| **Reference images** | `image_ref: "<bing query>"` per panel → `tools/news_image_ref.py` fetches a real photo → passed to nanobanana as a reference to redraw an original | Copyright-safe grounding for breaking-news visuals (real politicians, real product launches, etc.). Cached at `work/shorts/<sid>/panels/_refs/`. |

## Authoring a news short — concrete checklist

1. **Fetch source content**:
   - Recent Nikkei: `~/yt-pw/bin/python tools/news_fetch.py <URL> --out /tmp/article.json`
   - High-engagement headlines: `.venv/bin/python tools/x_trending.py --accounts BloombergJapan nikkei --hours 24 --require-url`
   - Read the body — narration must be **factually grounded** in the article.
2. **Write `projects/news_test_1/shorts/<sid>.yaml`**:
   - 12 panels with crisp single-beat prompts (photoreal-leaning).
   - Each `narration` entry is ~20-40 Japanese characters → ~3 sec audio at 1.25× speed.
   - Optional `image_ref: "<bing query>"` per panel for copyright-safe grounding (real people, breaking-news scenes).
   - Fields specific to news shorts:
     ```yaml
     image_style: photorealistic
     date_overlay: auto      # MM/dd today, top-right red badge (vertically centered)
     panels:
       - id: p1
         image_ref: "高市首相 記者会見"   # optional Bing reference
         prompt: |
           Photoreal …
     ja:
       voice_speed: 1.25
       voice_pitch: -0.10
       series_brand: "<topic-specific, ≤10 chars, NOT channel name>"
       hook_caption: "<shock/headline, ≤16 chars>"
       narration:
         - panel: p1
           text: "..."
           caption: "..."
     ```
3. **Generate**: `.venv/bin/python -m src.short_gen news_test_1 <sid>`
4. **HeyGen talking-head opener** (recommended for retention):
   ```bash
   .venv/bin/python tools/sync_anchor_opener.py \
     --backend heygen \
     --short projects/news_test_1/output/shorts/<sid>/ja/short.mp4 \
     --seconds 5 --in-place
   ```
   - The default `avatar_id` is the user's Newsroom Anchor look (`d996f26d…`); override with `--avatar-id` for other looks.
   - The opener gets the same hook/subtitle/date overlays as the rest of the short (see `apply_captions_to_opener` in the script).
   - To find your HeyGen avatar look IDs: `GET https://api.heygen.com/v3/avatars/looks?ownership=private` — the `id` field of each entry is what `/v3/videos` needs (NOT the `group_id` shown in the HeyGen UI).
5. **Upload**: `.venv/bin/python -m src.youtube_batch_upload_shorts news_test_1 --channel <ch_id> --only <sid> --privacy public` (API tokens already authorised; daily upload cap ≈10-12/day per [[feedback-youtube-api-quota]]).

## Topic → channel routing

Pick the right channel by the **dominant frame** of the story, not just the keyword:

- `baltoon_stocks_news_ja` — individual TYO/NYSE tickers, IPO mechanics, sector rotations (e.g., MLCC, semiconductors). NOT macro policy.
- `baltoon_crypto_news_ja` — BTC/ETH/SOL spot, stablecoins, on-chain incidents, JP crypto regulation. NOT just "company that invests in BTC".
- `baltoon_tech_news_ja` — product launches, AI model releases, EV/auto tech, semiconductor geopolitics (when chip is the protagonist). Skews 20代 hardest.
- `baltoon_politics_news_ja` — JP cabinet decisions, election news, budget/tax debates, foreign-policy stances. Tone neutral; avoid partisan framing.
- `baltoon_world_news_ja` — wars, summits, energy/commodity shocks, US-China dynamics. Frame "日本への影響" in the closing beat.

## Copyright safety (real people, recent news)

Real politicians (高市/トランプ), CEOs (ジェンスン・ファン/マスク), athletes, and breaking-news scenes are touchy. Two layers of protection:

1. **Image style abstraction**: For real people, prefer compositional descriptors ("a Japanese female prime minister at a Tokyo press podium, national flag behind her, formal navy attire") over named identification. nanobanana still produces a likeness because the context is unambiguous, but the prompt is generic.
2. **Reference-image-then-redraw** *(planned, not yet wired)*: Google Image Search for the topic → download top photo → pass to nanobanana as reference → it generates an original "in the style of" version. Avoids any direct reuse of source photos. Add via `image_ref: google:<query>` in the panel yaml when implemented.

For **paywalled-source narration**: the Nikkei/Bloomberg subscription cookies in `~/news-pw-profile` give us full article bodies through `news_fetch.py`. Use the source to **ground the facts**; rewrite freely in your own narration so the short is editorially original, not a copy.

## TTS reading safety (critical — see [[feedback-tts-readings]])

Even for news shorts, Aivis can mis-read:
- **後の世界** → ヨカイ (mis-segmentation `後の世`+`界`). Fix: write 「のちの世界」.
- **羽生さん** → ハブ (dictionary doesn't apply with `さん` suffix). Fix: write 「はにゅうさん」 in narration.
- Pre-flight: `tools/aivis_userdict.py` covers many names; for new ones (政治家・企業CEO・経済用語) verify reading via `/audio_query` moras before bulk generation.
- Post-flight: `~/flux2-mlx/bin/python tools/verify_tts.py news_test_1 <sid>` runs Whisper and prints the spoken text — catches obvious misreads.

**Regen after fixing**: deleting `output/shorts/<sid>/ja/short.mp4` is **not enough** — the per-segment audio is cached at `work/shorts/<sid>/ja/narration/seg_NN.mp3` keyed by index, not text. Always `rm -f work/shorts/<sid>/ja/narration/seg_*.mp3` too before re-running. (Burned twice in earlier sessions.)

## Pipeline summary

```
news_fetch.py / x_trending.py   →   topic + grounded body
              │
              v
  manual yaml authoring (12 panels, 1.5x, date_overlay, image_style)
              │
              v
  short_gen news_test_1 <sid>   →  short.mp4 (no talking head yet)
              │
              v
  sync_lipsync.py (optional)   →  prepends Sync.so anchor opener
              │
              v
  youtube_batch_upload_shorts --channel <ch>   →  published
              │
              v
  youtube_stats_sync + Redash refresh   →  next-day retention check
```

## Common pitfalls

- **Topic mismatch**: Politics short uploaded to stocks_news channel kills retention. Re-check `--channel` flag.
- **Date badge stale**: If you generate today and upload tomorrow, viewers see yesterday's MM/dd. Either regenerate the frames or override with explicit `date_overlay: "05/29"` to match upload date.
- **Brand new channel = no custom thumbnail**: Custom thumbnails require account verification + 4k-watch-hours or community standing. The 5 news channels still get the YouTube-autoselected thumbnail (silent 403 warning during upload is normal until verified).
- **Panel count too low → "slideshow" feel**: If a panel holds > 4 sec, viewers swipe. Audit before generation: `len(narration) >= 12 for 40-sec short`.
- **TTS misreads on political names**: 高市/石破/岸田 and recent ones must be reading-checked. See TTS section above.
