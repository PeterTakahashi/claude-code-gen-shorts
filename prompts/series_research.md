You are a researcher preparing source material for a serialized webtoon-style animated biography in Japanese.

**Subject:** {{subject}}

**Target audience / style:**
- First-person Japanese memoir voiceover (the subject themselves narrating from older age, looking back)
- 5-10 minutes per episode, ~25-35 panels each
- Anime / webtoon visual style, cinematic 16:9 stills
- Literary register that mixes third-person factual framing with first-person interior reminiscence
- K-drama emotional pacing

**Your job:** Produce a single JSON object capturing the raw source material. The downstream stages will use this to plan episodes and design cross-episode foreshadowing.

**Output a single JSON object. Output JSON only — no commentary, no markdown fences.**

Required top-level keys:

- `subject`: the person's name (Japanese form preferred for display)
- `birth_year`: integer
- `death_year_or_null`: integer or null
- `timeline`: array of 25-40 entries, chronologically ordered. Each entry:
  ```
  { "year": int, "age": int_or_null, "event": "short factual description in Japanese",
    "location": "place name in Japanese (カタカナ for non-Japanese places)",
    "emotional_significance": "one sentence on why this matters interiorly",
    "factual_certainty": "certain" | "approximate" | "uncertain" }
  ```
  Cover the full life. Include private events (relationships, near-failures, doubt) as well as public events. Do NOT invent — mark uncertain with `"uncertain"`.

- `key_characters`: array of objects. Include parents, siblings, spouses, key co-founders/partners, key adversaries.
  ```
  { "id": "snake_case_id", "name_ja": "name in katakana", "name_en": "Latin spelling",
    "role": "father|mother|brother|spouse|cofounder|...",
    "description_for_visual": "one sentence physical description for image generation (English)",
    "first_appears_when": "year or life-stage" }
  ```

- `core_themes`: array of 3-5 strings — the emotional questions that recur across the whole life. Examples: "the inner world made real", "the cost of obsession", "doors closing inside / opening again".

- `recurring_motifs`: array of objects.
  ```
  { "id": "snake_case_id", "description": "what the motif IS (visual, sensory, symbolic)",
    "why_significant": "the meaning that accrues to it across the life" }
  ```
  These should be SPECIFIC concrete things that can be returned to visually: a place, an object, a sound, a sensation.

- `key_quotes`: array of 5-10 objects. Real quotes (or close paraphrases of documented sentiments) that capture the subject's voice.
  ```
  { "ja": "Japanese rendering", "original": "original language phrasing",
    "when_said": "approximate year or context", "context": "circumstance" }
  ```

- `dramatic_high_points`: array of 8-15 specific events that are the natural dramatic centers — moments of greatest stakes, reversals, or revelations. These are the "must-include" scenes for the adaptation.
  ```
  { "id": "snake_case_id", "year": int, "title_ja": "short title",
    "why_dramatic": "one sentence on the stakes / emotional weight",
    "potential_climactic_image": "what the single most powerful frame might look like" }
  ```

Factual accuracy is critical. The downstream stages will rely on this. Output JSON only.
