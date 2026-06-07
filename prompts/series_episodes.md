You are designing a serialized webtoon-style animated biography in Japanese for the subject below.

**Subject:** {{subject}}
**Total episodes:** {{episode_count}}

**Format:**
- Each episode: 5-10 minutes, ~25-35 panels
- First-person Japanese memoir voiceover, anime/webtoon visuals, 16:9 stills
- Literary register: mix third-person factual framing ("1971年、〇〇") with first-person interior reminiscence ("僕は今でも覚えている…")
- K-drama-style frozen-fate cliffhanger ending on EVERY episode

---

## STRUCTURAL RULES (non-negotiable)

### Rule 1. Episode 1 opens with an in-media-res hook

Pick the single most dramatic, viewer-stopping moment from anywhere in the life — a moment of extreme physical/emotional stakes. Hold on it for 3-5 panels, then transition into chronological childhood narration with a clear pivot line ("どうしてここまで来てしまったのか — それを話すには、五歳のジャカランダの庭の話から始めなければならない" style). The hook should pay off later in the series in the episode where it chronologically occurs.

### Rule 2. Each episode ends with a frozen-fate cliffhanger

NOT a quiet contemplative moment. NOT a triumphant final image. NOT a viral comedy beat. The cliffhanger must be a **specific moment whose outcome is unknown to the viewer** — the very instant before resolution, frozen mid-action.

**Good cliffhanger examples (from existing chapters of this very project):**
- Rocket on launchpad, engines igniting, the LAST one they can afford — cut to black before liftoff (ch4)
- Falcon 1 stage separation: rocket arcing through dawn sky, all telemetry green so far, then... cut
- First stage descending toward landing zone, landing legs deploying, ground meters below — cut (ch6)
- Phone ringing in the dark, hand reaching for it, news that will change everything — cut
- Email opening on hotel honeymoon: "You are no longer the CEO" — frozen face — cut (ch3)

**Bad cliffhangers (AVOID):**
- Looking up at something beautiful (rocket on pad, stars)
- Holding a baby contemplatively
- Eating cup noodles
- A viral mishap (broken glass at product launch)
- A peaceful sunrise after a battle is won
- Pointing at a future goal

The cliffhanger MUST hinge on an unresolved binary: did it work / will they find out / will the relationship survive / will they make it in time. Outcome is decided in the NEXT episode.

### Rule 3. One central drama per episode

DO NOT cram 5-7 major events into one episode. Each episode should have ONE central tension — one question the episode is about, one emotional movement. Other events of the period are supporting context, not the spine. If an event is huge (Falcon Heavy, PayPal sale, a child's death), it should be the FOCUS, not a checkbox.

### Rule 4. Personal traumas matter as much as public ones

The most cinematic biographies weave private wounds into public events. Do NOT skip:
- Child deaths (e.g., 2004 Nevada Alexander Musk SIDS death is THE most emotionally weighted event of the subject's middle period — DO NOT skip)
- Parent/child estrangement (e.g., 2022 Vivian's public denunciation of her father — pays off Chapter 1's father-wound across the whole arc, MUST be included)
- Spousal collapse (Justine, Talulah twice, Grimes — each a private heart-event)

These are the emotional spine. Public events (rocket flies, company IPOs) ride on top.

### Rule 5. Plan the whole-series arc first, then episodes

Identify ONE overarching emotional question for the entire life (e.g., "can a child's inner world ever feel safe in the actual world?") — then design episodes that each contribute one movement of that question's exploration. Do NOT just summarize Wikipedia chronologically.

### Rule 6. The final episode does NOT tie everything up

A K-drama-quality series ends on a moment that promises THE NEXT BATTLE, not on a triumphant tableau. The final cliffhanger should leave the viewer convinced that the protagonist's story is unfinished — even if the subject is still alive, the narrative arc must end on an unresolved beat that resonates back to Chapter 1's wounds. Avoid: "all my children stand with me looking at Mars."

### Rule 7. Character introductions must pay off

Don't introduce a character who never returns. If a character is named in `characters_introduced`, they should appear in at least 2-3 episodes. Otherwise omit them and treat them as background.

---

## Already-completed episodes (FIXED — do not redesign these)

The existing chapters ch1-ch6 are already made. Plan future episodes to harmonize with them — pay off motifs/setup they planted, echo their lines/images, and respect their established cliffhangers. The existing chapters are:

{{existing_chapters}}

In your plan, include retrofit entries for ch1-ch6 that **reflect what's actually in their scenes.json** (don't invent different stories for them) — but feel free to note in `notes` how a future revision could improve them.

---

## Output format

For each episode output a JSON entry:
```json
{
  "id": "ch1" | "ch2" | ...,
  "title_ja": "string",
  "title_en": "string",
  "time_range": "e.g., 1971-1983",
  "ages_covered": "e.g., 0-12",
  "central_theme": "one sentence — the ONE question this episode is about",
  "emotional_arc": "one paragraph — emotional start → emotional end",
  "opening_hook": "specific scene. For ch1: the in-media-res moment. For ch2+: the first major beat.",
  "key_beats": ["6-12 specific events in order — fewer is better; ONE drama focus"],
  "climax": "the single most powerful moment of the episode",
  "cliffhanger": "the frozen-fate moment that ends the episode — must satisfy Rule 2 above",
  "characters_introduced": ["character ids — must reappear later per Rule 7"],
  "characters_returning": ["character ids"],
  "motifs_planted": ["motif ids planted/introduced here"],
  "motifs_paid_off": ["motif ids whose meaning gets transformed/answered here"],
  "callbacks_to_earlier_episodes": ["specific previous-episode beats this episode echoes"],
  "notes": "free-form design notes — including what could be improved on revision"
}
```

**Output a JSON array of exactly {{episode_count}} episode objects.** JSON only, no commentary, no markdown fences.

---

## Research input

```json
{{research_json}}
```
