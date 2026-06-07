"""Generation-only constants. Per-project paths/style live in project.yaml."""
from __future__ import annotations

GEMINI_MODEL = "gemini-3.1-flash-image-preview"
N_CANDIDATES_PER_PANEL = 4
N_CANDIDATES_PER_CHARACTER = 4
SCORE_THRESHOLD = 42
MAX_RETRY_ROUNDS = 3

# Aspect-ratio presets keyed by shot_type — image-gen prompts use these as
# defaults when a panel doesn't specify aspect_ratio explicitly.
DEFAULT_ASPECT_RATIOS = {
    "wide_establishing": "16:9",
    "medium": "4:5",
    "close_up": "4:5",
    "extreme_close_up_eyes": "2:1",
    "full_body": "3:4",
    "climax": "1:2",
}
