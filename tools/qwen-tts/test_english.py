"""First-run smoke test for Qwen3-TTS local English generation.

The first invocation downloads the model (~1.7B params ≈ 3-4 GB).
Use --device cpu if MPS hits an unsupported op.
"""
import argparse
import time
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--text", default="Hello world. This is a Qwen TTS smoke test on Apple Silicon. The quick brown fox jumps over the lazy dog.")
    p.add_argument("--speaker", default="Ryan", choices=["Ryan", "Aiden"])
    p.add_argument("--device", default="mps", choices=["mps", "cpu", "cuda"])
    p.add_argument("--out", type=Path, default=Path("output.wav"))
    args = p.parse_args()

    dtype = torch.bfloat16 if args.device != "cpu" else torch.float32
    print(f"loading Qwen3-TTS on {args.device} / dtype={dtype} …")
    started = time.time()
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        device_map=args.device,
        dtype=dtype,
    )
    print(f"  loaded in {time.time()-started:.1f}s")

    print(f"generating: {args.speaker} → {args.out}")
    started = time.time()
    wavs, sr = model.generate_custom_voice(
        text=args.text,
        language="English",
        speaker=args.speaker,
    )
    print(f"  generated in {time.time()-started:.1f}s (sample_rate={sr}, samples={wavs[0].shape})")
    sf.write(str(args.out), wavs[0], sr)
    print(f"  wrote: {args.out}  ({args.out.stat().st_size//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
