---
name: cautionary-tale-webtoon
description: Produce Japanese "failure-story" (失敗談 / 後悔 / 警告) Shorts where an ordinary person makes a relatable mistake, spirals into disaster, and the short ends on how it could have been avoided. Invoke for "失敗談の動画", "後悔ショート", "住宅ローン地獄", "make a cautionary tale short", or building/extending the housing_regret / money_failure / cosmetic_regret channels. Shorts-first (each short is one self-contained 30-45s story). The avoidance/lesson beat is mandatory — it is both the satisfying payoff AND the native-ad slot for the vertical's advertisers (FP, 借り換え, リフォーム, 弁護士, クリニック). Stack: Gemini 2.5 Flash Image (panels), Aivis TTS, ffmpeg, YouTube Data API. Reuses the short_gen.py pipeline.
---

# cautionary-tale-webtoon — relatable failure stories that end on "how to avoid it"

Use this skill in the `webtoon-gen` repo to build **consumer cautionary-tale** Shorts: a normal Japanese person makes a mistake the viewer could plausibly make, it spirals, and the short closes on the lesson. The verticals are chosen for **large advertiser markets** (housing, personal finance, cosmetic) — the failure story is, by construction, the setup for the advertiser's product as the solution.

This is **distinct from the sibling skills**:
- `biography-webtoon` — one real person's life, *rise* arc, 12-episode long-form.
- `corporate_fall` / `corporate_incidents` projects — companies collapsing. The viewer is a spectator, so there is **no "you could avoid this" beat**.
- **This skill** — the protagonist is an *everyman stand-in for the viewer*. So it adds two beats corporate failure stories don't have: **自分ごと化 (relatability)** and **回避法 (the lesson/escape)**. Those two beats are the whole point.

## The win-win / native-ad principle (read this first)

Fear is the hook; the lesson is the payoff. **The first half stokes anxiety, the second half MUST land on how to avoid it.** Breaking this rule breaks the channel three ways:
1. A short with no resolution feels bad → lower completion → swiped (violates the `youtube-shorts` rule: setup → climax → **resolution**).
2. Pure doom-mongering is reputationally toxic and YPP-unfriendly.
3. The lesson beat *is* the future client's ad slot: 住宅ローン地獄 → 「借り換え/FP相談で防げた」(FP・住宅ローン会社); 借金地獄 → 「早く相談すれば」(債務整理弁護士=JP最高単価); 整形失敗 → 「医院選び・カウンセリング」(クリニック). Build every short so the avoidance beat names a *category* of solution, never improvises advice.

## The failure arc — 7 beats (this is the format IP)

This replaces biography's "rise + cliffhanger". Each Short follows it:

| # | Beat | Purpose | Image / caption |
|---|---|---|---|
| 1 | **着地点を先に見せる (cold-open crater)** | Stop the swipe. Show the *outcome* before the fall. | Shocking image (empty/foreclosed house, court notice, ruined face). Caption = the punch ("築3年で手放した") |
| 2 | **自分ごと化 (relatability)** | Make the viewer think "私もやりそう". | Ordinary protagonist: "年収550万・共働き・35歳の普通の家庭でした" |
| 3 | **運命の選択 (the fatal decision)** | The mistake — framed so it looks *reasonable* at the time. | The contract signed, the dream, the optimistic projection |
| 4-5 | **転落のスパイラル (the spiral)** | Stoke anxiety, factual escalation. 2-3 panels. | Each consequence worse than the last |
| 6 | **どん底 (rock bottom)** | The climax — return toward the cold-open image (loop point). | The crater, now understood |
| 7 | **回避法 / 教訓 (the escape — MANDATORY)** | The payoff + the ad slot. Name the *category* of fix. | "返済比率は手取りの20%まで。変動なら金利上昇を試算。迷ったら早めにFPへ" |

No end card (Shorts loops; beat 6 ≈ beat 1 = seamless loop). Panel density: `panels ≈ total_sec ÷ 3.5` (a 35s short ≈ 10 panels) — split JA narration into short beats, one image per beat.

## Safety guardrails (keep the channels monetizable and out of court)

- **Stories + general lessons, never specific advice.** No "buy this", no "this clinic", no medical claims, no "this investment returns X%". The lesson beat names a *category* of professional ("FPに相談", "債務整理に詳しい弁護士へ"), not an instruction.
- **Cosmetic (`cosmetic_regret`) is highest-risk** — avoid medical claims and graphic before/after; frame as "医院選び・カウンセリングの物語". Build it *last*, after the format is proven on housing/finance.
- **Fictionalized composites.** Protagonists are invented everymen, not real named victims. Don't depict real brands/companies as villains (defamation) — use generic 工務店 / 銀行 / クリニック.
- Inherit all biography image rules: **no Japanese text inside images**, explicit Japan setting in `background_style`, anatomy negatives in `project.yaml`.

## Verticals

| theme (channel) | status | core stories | avoidance beat → advertiser |
|---|---|---|---|
| `housing_regret` | **building now** | 住宅ローン地獄 / 注文住宅で後悔 / 欠陥住宅 / 近隣トラブル / 不動産投資の罠 | 返済比率・借り換え・FP・打合せチェックリスト → FP/銀行/リフォーム/HM |
| `money_failure` | planned next | 借金地獄 / 投資詐欺 / リボ沼 / 奨学金 / FX大損 | 早期相談・債務整理・分散 → 弁護士(最高CPM)/証券/保険 |
| `cosmetic_regret` | planned (careful) | 整形の後悔 / 脱毛トラブル / 美容ローン | 医院選び・カウンセリング → クリニック |

### Housing hook bank (story seeds)
1. ペアローン×変動金利×フルローン → 産休で世帯収入減 → 競売 (the flagship; see `housing-loan-hell-pair`)
2. 注文住宅の動線・コンセント・日当たりの後悔 (light, highly relatable, low risk)
3. 「相場より安い」中古を即決 → 雨漏り・シロアリ・基礎の欠陥
4. ボーナス払い前提のローン → ボーナスカットで破綻
5. 義両親と二世帯 → 設計で揉め、売るに売れない
6. 駅近の小さな土地に無理な3階建て → 老後に階段地獄
7. 新築マンション購入直後の大規模修繕積立金の急騰
8. 「家賃並みの返済」セールストークを鵜呑み → 維持費(固定資産税・修繕)で破綻

## Repo entrypoints (reuse the shorts pipeline — don't reinvent)

Same `short_gen.py` as `youtube-shorts`. Cautionary shorts are **regenerate-only** (no long-form to `reuse:` from), so panels carry a `prompt:`.

| Command | What it does |
|---|---|
| `uv run python -m src.short_gen housing_regret <short_id>` | Build one short from `projects/housing_regret/shorts/<short_id>.yaml` |
| `uv run python -m src.short_gen housing_regret --all --batch` | Build every short, panels via Gemini Batch API (50% off, 20-60min) |
| `uv run python -m src.short_translate housing_regret --all` | Add `i18n.en` (only if/when EN channels resume — currently JA-only) |
| `uv run python -m src.youtube_batch_upload_shorts housing_regret --channel baltoon_housing_regret_ja` | Upload to the housing channel |

## Project layout

```
projects/housing_regret/
  project.yaml          # shorts-only, anime style, narrator config (mirror corporate_fall)
  characters.yaml       # reusable everyman archetypes for visual consistency
  shorts/<id>.yaml      # one failure story each (v2 schema: panels[].prompt + ja.narration[])
  output/shorts/<id>/ja/short.mp4
```

A short's yaml uses the **v2 schema**: top-level `panels:` with `id` + `prompt`, and a `ja:` block with `title / description / hook_caption / series_brand / voice_speed / narration[]` where each narration entry is `{panel, text, caption}`. See `projects/housing_regret/shorts/housing-loan-hell-pair.yaml` as the reference exemplar (built to the 7-beat arc + all writing rules).

## Writing rules (inherited from user memory — enforce in every short)

- **Connective adult prose**, not a list of past-tense sentences. Use `だったので`, `から`, `しかし`, `結果として`. Explain *why* the mistake felt reasonable.
- **Year + relative time**: "10年後の20XX年", "翌年", "それから半年" — never a bare year.
- **Subtitle conventions**: people/places katakana; companies/products English; dates/numbers Arabic.
- **Reduce `、`** — only at natural breath breaks; never 3+ in one sentence.
- **Shocking p1** — beat 1 must be a striking image (beautiful/ruined/extreme close-up) or the feed skips it in 0.5s.
- **Caption ≤ ~18 chars**, one line. Hook caption persists; `series_brand` (e.g. 「住宅の後悔」) sits under it.

## Channel registration (your steps — needs a real YouTube channel + OAuth)

The `housing_regret` theme is already added to the live DB + `db/init/001_schema.sql`, and SFX defaults are in `short_gen.py`. To go live:

1. Create the YouTube channel in your Google account (e.g. display name 「住宅の後悔 / Baltoon」).
2. OAuth: produce `.youtube_token.baltoon_housing_regret_ja.json` at repo root (run an upload once; `PYTHONUNBUFFERED=1` so the auth URL prints — see memory `feedback_python_oauth_buffering`).
3. Register the channel row:
   ```python
   from src.db import connect, upsert_channel
   with connect() as conn:
       upsert_channel(conn, channel_id="baltoon_housing_regret_ja",
                      youtube_channel_id="UC...", display_name="住宅の後悔",
                      theme="housing_regret", language="ja",
                      oauth_token_file=".youtube_token.baltoon_housing_regret_ja.json")
   ```
4. Add the channel link in `src/youtube_update_metadata.py` `CHANNEL_LINKS` if you want footer links.

## Cadence & cost

- Post 3-5 shorts/day to feed the algorithm (memory: <35s performs +43%, fast opening cut).
- ~6-10 regenerate panels/short × $0.039 (batch) = **~$0.25-0.40/short**; TTS + compose free.
- Mind the shared YouTube API quota (~30 short uploads/day across all channels; resets 15:00 JST).

## Recovery / common issues

| Symptom | Fix |
|---|---|
| Panel `no image returned` | re-render that scene; remove real-brand/logo references from the `prompt`, generalize |
| Short feels preachy / flat | front-load the crater (beat 1), keep the spiral concrete, make the lesson one crisp line |
| Lesson sounds like advice | rephrase to "相談先のカテゴリ" not an instruction (guardrails above) |
| Image shows Japanese text | add `No Japanese text in image` to the prompt; rerun |
| Re-cut narration but length/audio unchanged | per-segment TTS is cached **by index** at `work/shorts/<id>/<lang>/narration/seg_*.mp3` — `rm` those + the output `narration*.mp3` and `short.mp4`, then re-run **without** `--force`. (`--force` also regenerates panel images = extra cost + different faces.) Panel image cache lives separately at `work/shorts/<id>/panels/` and is reused as long as you don't `--force`. |

## Related

- `youtube-shorts` — base shorts spec (panel density, captions, loop, opening cut). This skill is its cautionary-tale specialization.
- `biography-webtoon` — sibling; shares the pipeline and image/prose rules.
- User memory `MEMORY.md` — shocking p1, caption y-offset, fast opening cut, JA-only operation (2026-05), subtitle conventions.
