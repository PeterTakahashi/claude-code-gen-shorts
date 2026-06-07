"""Smoke test: load Kokoro-82M, synthesize one utterance to /tmp/kokoro_test.wav."""
import sys
from pathlib import Path
import soundfile as sf
import torch

from kokoro import KPipeline

text = sys.argv[1] if len(sys.argv) > 1 else "He made a stunning 44 billion dollar offer to buy Twitter outright."
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/kokoro_test.wav")
voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"

print(f"loading pipeline (lang=a / American English) …")
pipeline = KPipeline(lang_code="a")
print(f"synthesizing voice={voice} text={text!r}")
chunks = []
for _, _, audio in pipeline(text, voice=voice, speed=1.0):
    chunks.append(audio if isinstance(audio, torch.Tensor) else torch.as_tensor(audio))
audio = torch.cat(chunks).cpu().numpy()
sf.write(out, audio, 24000)
print(f"wrote {out}  ({len(audio)/24000:.1f}s)")
