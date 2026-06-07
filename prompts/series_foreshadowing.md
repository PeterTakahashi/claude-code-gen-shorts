You are designing the foreshadowing / payoff chains for a serialized webtoon-style animated biography.

**Subject:** {{subject}}

**Your job:** Given the episode plan below, identify 10-15 cross-episode foreshadowing chains.

Each chain:
- Plants something CONCRETE in an early episode (visual, line, object, character beat) — not abstract themes
- Reinforces / transforms it through middle episodes
- Pays off in a later episode with recognition, reversal, or resolution

---

## Strong chain criteria

- Spans 4+ episodes
- Plants something **concrete and specific** (a specific object, a specific phrase, a specific gesture, a specific room) — not abstractions like "innovation" or "leadership"
- The meaning of the planted thing **transforms** across the chain (a check that means "proof" in ch1 becomes "fuel" in ch3 becomes "what is the next thing for?" in ch5)
- The final payoff **resolves an emotional question** the viewer has been carrying

---

## MANDATORY chains for this series (must be included)

For a serialized biography of a complex public figure, the following chain TYPES are required. Construct each one from the episode plan, ensuring concrete beats in specific episodes:

1. **"心の中の扉が閉じる/開く" (doors inside closing and opening)** — a specific recurring INTERIOR door image planted at the first emotional wound (typically a parental or childhood beat), echoed at each major betrayal/coup the subject experiences in their career, finally REOPENED (or, devastatingly, ECHOED in REVERSE) when the subject finds themselves acting as the wound-giver to the next generation. This chain is the spine of the entire psychological arc.

2. **"繰り返される場所/モチーフ" (a returning physical place or motif)** — pick a specific evocative location/object from the subject's childhood (e.g., a particular garden, a specific room, a particular tree). Plant it in the very first panel of ch1. Bring it back as a translucent overlay / memory / actual return at least 3 times across the series, with its meaning shifting each time (innocence → resignation → defiant return).

3. **"自分が、なりたくなかった親に、なっていた" (becoming the parent we feared)** — plant a specific damaging line from a parent in ch1 ("お前にも非がある" type). Echo the line said BY the protagonist to someone else mid-series. Climactic payoff is the moment the protagonist HEARS THEIR OWN VOICE doing what their parent did, and either fails to apologize or succeeds in breaking the pattern.

4. **"通貨の意味の変遷" (the meaning of money transforming)** — plant a specific small amount early (e.g., $500 check at age 12 = "proof inner world is real"). Echo at each major financial gate the subject crosses ($22M at company sale = "fuel", $180M at next sale = "what is this for?"). Each amount means something DIFFERENT to the protagonist's interior. The payoff is the moment a much larger amount means LESS than the first one did.

In addition to those four mandatory chains, design 6-11 more chains specific to this subject's life and the episode plan provided.

---

## Output format

```json
{
  "id": "snake_case_id",
  "description": "what this chain is and the emotional question it carries",
  "type": "object" | "phrase" | "character_relationship" | "setting" | "emotion" | "gesture" | "color_palette" | "sound",
  "intended_emotional_arc": "one sentence — the journey from plant to payoff",
  "chain": [
    {
      "episode": "chN",
      "beat": "specific concrete description of how it manifests in this episode",
      "role": "plant" | "echo" | "transform" | "payoff" | "final"
    },
    ...
  ]
}
```

**Output a JSON array of 10-15 chain objects.** Order by emotional importance (most important first). JSON only, no commentary, no markdown fences.

---

## Research (for context)

```json
{{research_json}}
```

## Episode plan

```json
{{episodes_json}}
```
