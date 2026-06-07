"""Persistent FLUX.2 batch generator — load the model ONCE, generate many panels.

Runs inside the dedicated arm64 mflux venv (~/flux2-mlx). The main webtoon-gen
process shells out to this with a JSON job file so all panels of a run share a
single model load (vs the per-CLI-call reload that made flux2-local ~6x slower).

Usage:
  python flux2_batchgen.py <jobs.json> [model] [quantize] [steps] [size]

jobs.json: [{"prompt": "...", "output": "/abs/path.png", "seed": 123}, ...]
Prints one "OK i/n <path>" or "FAIL i/n <path>: <err>" line per job.
"""
import json
import os
import sys

from mflux.models.common.config import ModelConfig
from mflux.models.flux2.variants import Flux2Klein
from mflux.utils.image_util import ImageUtil

# Pre-quantized model saved by `Flux2Klein.save_model` loads in ~1s (vs ~3.4min
# for on-the-fly quantization). Prefer it if present.
_DEFAULT_SAVED = os.path.expanduser("~/flux2-mlx/models/flux2-klein-4b-q4")


def main() -> int:
    jobs_path = sys.argv[1]
    model_name = sys.argv[2] if len(sys.argv) > 2 else "flux2-klein-4b"
    quantize = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    steps = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    size = int(sys.argv[5]) if len(sys.argv) > 5 else 1024

    with open(jobs_path) as f:
        jobs = json.load(f)

    saved = os.environ.get("FLUX2_MODEL_PATH") or (_DEFAULT_SAVED if os.path.isdir(_DEFAULT_SAVED) else None)
    if saved:
        print(f"loading SAVED q4 model {saved} (~1s) once for {len(jobs)} job(s)…", flush=True)
        model = Flux2Klein(
            model_config=ModelConfig.from_name(model_name=model_name),
            quantize=None, model_path=saved, lora_paths=None, lora_scales=None,
        )
    else:
        print(f"loading {model_name} (q{quantize}, on-the-fly) once for {len(jobs)} job(s)…", flush=True)
        model = Flux2Klein(
            model_config=ModelConfig.from_name(model_name=model_name),
            quantize=quantize, model_path=None, lora_paths=None, lora_scales=None,
        )

    n = len(jobs)
    for i, job in enumerate(jobs, 1):
        try:
            image = model.generate_image(
                seed=int(job["seed"]),
                prompt=job["prompt"],
                num_inference_steps=steps,
                width=size, height=size,
                guidance=1.0,
                scheduler="flow_match_euler_discrete",
            )
            ImageUtil.save_image(image=image, path=job["output"], export_json_metadata=False)
            print(f"OK {i}/{n} {job['output']}", flush=True)
        except Exception as e:
            print(f"FAIL {i}/{n} {job['output']}: {e}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
