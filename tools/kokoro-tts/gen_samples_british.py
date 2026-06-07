"""Generate Kokoro-82M British-English samples for A/B comparison."""
from pathlib import Path
import soundfile as sf
import torch

from kokoro import KPipeline

OUT = Path("/tmp/kokoro_samples_british")
OUT.mkdir(parents=True, exist_ok=True)

SAMPLES = [
    ("numbers_2008",    "By 2008, SpaceX's first three rocket launches had all ended in explosive failure."),
    ("numbers_44b",     "He made a stunning 44 billion dollar offer to buy Twitter outright."),
    ("boarding",        "Jensen Huang dropped out of Kentucky boarding school at the age of 16."),
    ("date_sep28",      "On September 28th, the Falcon 1 finally reached orbit."),
    ("twitter_journey", "His journey to buy the company didn't start with a bang, but with a simple offer: a seat on the board."),
]

# British male + female voices.
VOICES = ["bm_george", "bm_lewis", "bm_daniel", "bm_fable",
          "bf_emma", "bf_isabella", "bf_alice", "bf_lily"]

pipeline = KPipeline(lang_code="b", repo_id="hexgrad/Kokoro-82M")

for name, text in SAMPLES:
    for voice in VOICES:
        out = OUT / f"{name}__{voice}.wav"
        chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=1.0):
            chunks.append(audio if isinstance(audio, torch.Tensor) else torch.as_tensor(audio))
        audio = torch.cat(chunks).cpu().numpy()
        sf.write(out, audio, 24000)
        print(f"{out.name}  ({len(audio)/24000:.1f}s)")
