#!/usr/bin/env python3
# File: scripts/infer_sdxl.py
# Version: 1.0.0
# Description: All benchmark profiles load real SDXL; tiny is an explicit setup self-test only.
# Execution: .venv/bin/python scripts/infer_sdxl.py --backend sdxl --image-resolution 1024 --num-inference-steps 50
# Options: --backend, --model-name, --precision, --scheduler, --prompt-source, --prompt-len, --image-resolution, --batch-size, --num-images, --num-inference-steps, --guidance-scale, --seed, --output
# Requirements: Python 3.12, PyTorch, diffusers, and cached SDXL weights.
# Environment: Repository-local .venv after setup.sh. HF_HOME defaults to .cache/huggingface.
# Dependencies: torch, diffusers, transformers
# Repository: gpu-bench-amd-sdxl-diffusers-latency / gpu-bench-nvidia-sdxl-diffusers-latency
# License: Apache-2.0

from __future__ import annotations

import argparse
import csv
import io
import math
import os
import time
import warnings
from pathlib import Path

# Quiet library output. These were printed on every run: "Loading weights" bars,
# transformers' torchvision fallback notes, diffusers' FutureWarnings (torch_dtype,
# upcast_vae) and six "modules in AutoencoderKL that should be kept in float32"
# warnings. The settings are read when the libraries are imported, so they come
# first. Errors and tracebacks still print.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("DIFFUSERS_VERBOSITY", "error")

import torch
import torch.nn as nn

# diffusers' deprecation notices (torch_dtype, upcast_vae) are FutureWarnings
# raised when diffusers is used; it is imported later, inside the functions.
warnings.filterwarnings("ignore", category=FutureWarning)


SDXL_HF_ID = "stabilityai/stable-diffusion-xl-base-1.0"
SYNTHETIC_PROMPT = "a photograph of a red cube on a wooden table, studio lighting"


def mark_measure_start() -> None:
    """Setup ends here: record when the timed work starts (TEMPLATE_00_141).

    run_benchmark.sh reads BENCHMARK_MEASURE_START_FILE when the benchmark stops and
    starts the benchmark clock at this time, so model load and warmup count as setup.
    The first call of a run wins. Outside run_benchmark.sh it does nothing.
    """
    import os
    import time

    path = os.environ.get("BENCHMARK_MEASURE_START_FILE", "")
    if not path or os.path.exists(path):
        return
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"{time.time_ns()}\n")
    except OSError:
        pass


def sized_prompt(length: str) -> str:
    """Repeat the synthetic prompt out to prompt_len words."""
    words = SYNTHETIC_PROMPT.split()
    try:
        count = max(1, int(float(length)))
    except (TypeError, ValueError):
        return SYNTHETIC_PROMPT
    if count <= len(words):
        return " ".join(words[:count])
    padded = list(words)
    while len(padded) < count:
        padded.append(words[len(padded) % len(words)])
    return " ".join(padded)
LATENT_CHANNELS = 4
MIN_REAL_RESOLUTION = 256
MIN_TIMED_IMAGES = 2
MIN_SDXL_VRAM_GB = 5.0


class TinyDenoiser(nn.Module):
    def __init__(self, channels: int = LATENT_CHANNELS) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(channels, 16, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(16, 16, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(16, channels, 3, padding=1),
        )

    def forward(self, latents: torch.Tensor, _timestep: torch.Tensor) -> torch.Tensor:
        return self.net(latents)


def yaml_token(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    if text.lower() == "true":
        return "true"
    if text.lower() == "false":
        return "false"
    return text


def effective_int(value: object, true_default: int) -> int:
    token = yaml_token(value)
    if token == "true":
        return true_default
    return max(1, int(float(token)))


def resolve_dtype(precision: str) -> torch.dtype:
    token = precision.lower()
    if "bf16" in token or "bfloat16" in token:
        return torch.bfloat16
    if "32" in token:
        return torch.float32
    return torch.float16


def resolve_hf_id(model_name: str) -> str:
    token = str(model_name).strip()
    if token == "sdxl-base-1.0":
        return os.environ.get("SDXL_HF_ID", SDXL_HF_ID)
    if "/" in token:
        return token
    raise SystemExit(f"[FAIL] model_name must be sdxl-base-1.0 or a Hugging Face id; got {model_name}")


def finite_nonneg(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        return 0.0
    return parsed


def peak_torch_memory_gb(device: torch.device) -> float:
    if not torch.cuda.is_available():
        return 0.0
    return max(
        torch.cuda.max_memory_allocated(device),
        torch.cuda.max_memory_reserved(device),
    ) / 1e9


def result_line(params: dict[str, object], metrics: dict[str, float], status: str = "ok") -> str:
    parts = ["RESULT"]
    for key, value in params.items():
        parts.append(f"{key}={value}")
    for key, value in metrics.items():
        parts.append(f"{key}={value:.6f}")
    parts.append(f"status={status}")
    return " ".join(parts)


def write_csv(path: Path | None, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "sample_index",
        "status",
        "latency_ms",
        "images_per_sec",
        "gpu_mem_gb",
        "step_time_ms",
        "error_message",
    ]
    print("# CSV")
    print(",".join(fieldnames))
    for row in rows:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerow([row[name] for name in fieldnames])
        print(buf.getvalue(), end="")
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_tiny(
    device: torch.device,
    dtype: torch.dtype,
    resolution: int,
    steps: int,
    num_images: int,
    seed: int,
) -> tuple[list[dict[str, object]], dict[str, float]]:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.cuda.reset_peak_memory_stats(device)
    model = TinyDenoiser().to(device=device, dtype=dtype)
    model.eval()
    dt = 1.0 / steps
    rows: list[dict[str, object]] = []
    first_latency_ms = 0.0
    mark_measure_start()  # setup ends: model loaded, warmup done
    with torch.no_grad():
        for image_index in range(num_images):
            latents = torch.randn(1, LATENT_CHANNELS, resolution, resolution, device=device, dtype=dtype)
            if torch.cuda.is_available():
                torch.cuda.synchronize(device)
            t0 = time.perf_counter()
            for step in range(steps):
                timestep = torch.tensor([step], device=device, dtype=dtype)
                latents = latents - dt * model(latents, timestep)
            if torch.cuda.is_available():
                torch.cuda.synchronize(device)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if image_index == 0:
                first_latency_ms = latency_ms
            gpu_mem_gb = peak_torch_memory_gb(device)
            rows.append(
                {
                    "sample_index": image_index,
                    "status": "ok",
                    "latency_ms": latency_ms,
                    "images_per_sec": 1000.0 / latency_ms if latency_ms > 0 else 0.0,
                    "gpu_mem_gb": gpu_mem_gb,
                    "step_time_ms": latency_ms / steps,
                    "error_message": "",
                }
            )
    mean_latency_ms = sum(float(row["latency_ms"]) for row in rows) / len(rows)
    peak = max(float(row["gpu_mem_gb"]) for row in rows)
    metrics = {
        "per_image_latency_sec": finite_nonneg(mean_latency_ms / 1000.0),
        "images_per_sec": finite_nonneg(1000.0 / mean_latency_ms if mean_latency_ms > 0 else 0.0),
        "peak_vram_gb": finite_nonneg(peak),
        "first_image_latency_sec": finite_nonneg(first_latency_ms / 1000.0),
        "step_time_ms": finite_nonneg(mean_latency_ms / steps),
    }
    return rows, metrics



def _local_sdxl_snapshot(hf_id: str) -> str:
    """Return the cached snapshot directory for hf_id, or hf_id itself.

    install_sdxl_python.sh --prefetch downloads only the fp16 Diffusers files.
    Newer huggingface_hub rejects that partial snapshot by repo id with
    local_files_only=True (IncompleteSnapshotError, missing fp32 siblings).
    Loading the snapshot directory directly skips that Hub completeness check.
    """
    if os.path.isdir(hf_id):
        return hf_id
    try:
        from huggingface_hub import constants as hf_constants

        cache = Path(hf_constants.HF_HUB_CACHE)
    except Exception:  # noqa: BLE001
        cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    snaps = cache / ("models--" + hf_id.replace("/", "--")) / "snapshots"
    if snaps.is_dir():
        for snap in sorted(snaps.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if (snap / "model_index.json").is_file() and (snap / "unet" / "diffusion_pytorch_model.fp16.safetensors").is_file():
                return str(snap)
    return hf_id

def run_sdxl(
    device: torch.device,
    dtype: torch.dtype,
    hf_id: str,
    scheduler_name: str,
    prompt: str,
    resolution: int,
    steps: int,
    num_images: int,
    batch_size: int,
    guidance_scale: float,
    seed: int,
) -> tuple[list[dict[str, object]], dict[str, float]]:
    cold_start = time.perf_counter()
    from diffusers import EulerDiscreteScheduler, StableDiffusionXLPipeline
    from diffusers.utils import logging as diffusers_logging

    diffusers_logging.disable_progress_bar()  # "Loading pipeline components..." (no env switch)

    if scheduler_name.lower() != "euler":
        raise SystemExit("[FAIL] scheduler must remain euler for this workload.")
    local_only = os.environ.get("HF_HUB_OFFLINE", "").strip() in {"1", "true", "TRUE"}
    if local_only:
        hf_id = _local_sdxl_snapshot(hf_id)
        print(f"[INFO] SDXL load source: {hf_id}")
    load_kwargs = {
        "torch_dtype": dtype,
        "use_safetensors": True,
        "local_files_only": local_only,
    }
    try:
        pipe = StableDiffusionXLPipeline.from_pretrained(
            hf_id,
            variant="fp16" if dtype == torch.float16 else None,
            **load_kwargs,
        )
    except (OSError, ValueError):
        pipe = StableDiffusionXLPipeline.from_pretrained(hf_id, **load_kwargs)
    pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config)
    pipe.safety_checker = None
    pipe.set_progress_bar_config(disable=True)
    pipe = pipe.to(device)
    if steps < 2:
        raise SystemExit("[FAIL] num_inference_steps must be at least 2 to time a denoising step.")
    generator = torch.Generator(device=device).manual_seed(seed)
    # #5 First-image latency, cold: the warmup call is one full image at the
    # yaml step count and it is timed, so it includes one-time kernel compile /
    # autotune and weight placement. (It used to be an untimed 2-step call, and
    # the reported "first image" was a later, already-warm image.)
    if torch.cuda.is_available():
        torch.cuda.synchronize(device)
    with torch.no_grad():
        pipe(
            prompt=prompt,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            height=resolution,
            width=resolution,
            generator=generator,
            output_type="pil",
        )
    if torch.cuda.is_available():
        torch.cuda.synchronize(device)
    first_latency_ms = (time.perf_counter() - cold_start) * 1000.0
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats(device)

    mark_measure_start()  # setup ends: model loaded, warmup done
    # #4 Denoising step time: diffusers calls this at the end of every
    # denoising step. The time between the first and last call, divided by the
    # intervals, is scheduler + UNet time for one step of the whole batch,
    # without text encoders, VAE decode, or image conversion.
    step_marks: list[float] = []

    def step_timer(_pipe, _step, _timestep, callback_kwargs):
        if torch.cuda.is_available():
            torch.cuda.synchronize(device)
        step_marks.append(time.perf_counter())
        return callback_kwargs

    batch_step_times: list[float] = []

    rows: list[dict[str, object]] = []
    remaining = num_images
    image_index = 0
    while remaining > 0:
        this_batch = min(batch_size, remaining)
        prompts = [prompt] * this_batch
        generator = torch.Generator(device=device).manual_seed(seed + image_index)
        if torch.cuda.is_available():
            torch.cuda.synchronize(device)
        step_marks.clear()
        t0 = time.perf_counter()
        with torch.no_grad():
            pipe(
                prompt=prompts,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
                height=resolution,
                width=resolution,
                generator=generator,
                output_type="pil",
                callback_on_step_end=step_timer,
            )
        if torch.cuda.is_available():
            torch.cuda.synchronize(device)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if len(step_marks) < 2:
            raise SystemExit(f"[FAIL] denoising step callback ran {len(step_marks)} time(s); expected {steps}.")
        step_ms = (step_marks[-1] - step_marks[0]) * 1000.0 / (len(step_marks) - 1)
        batch_step_times.append(step_ms)
        per_image_ms = latency_ms / this_batch
        gpu_mem_gb = peak_torch_memory_gb(device)
        for offset in range(this_batch):
            rows.append(
                {
                    "sample_index": image_index + offset,
                    "status": "ok",
                    "latency_ms": per_image_ms,
                    "images_per_sec": 1000.0 / per_image_ms if per_image_ms > 0 else 0.0,
                    "gpu_mem_gb": gpu_mem_gb,
                    "step_time_ms": step_ms,
                    "error_message": "",
                }
            )
        remaining -= this_batch
        image_index += this_batch

    mean_latency_ms = sum(float(row["latency_ms"]) for row in rows) / len(rows)
    peak = max(float(row["gpu_mem_gb"]) for row in rows)
    metrics = {
        "per_image_latency_sec": finite_nonneg(mean_latency_ms / 1000.0),
        "images_per_sec": finite_nonneg(1000.0 / mean_latency_ms if mean_latency_ms > 0 else 0.0),
        "peak_vram_gb": finite_nonneg(peak),
        "first_image_latency_sec": finite_nonneg(first_latency_ms / 1000.0),
        "step_time_ms": finite_nonneg(sum(batch_step_times) / len(batch_step_times)),
    }
    return rows, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Time SDXL inference or a tiny smoke stand-in")
    parser.add_argument("--backend", default="", help="sdxl for benchmark runs; tiny is a setup self-test.")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--model-name", dest="model_name", default="sdxl-base-1.0")
    parser.add_argument("--precision", default="fp16")
    parser.add_argument("--scheduler", default="euler")
    parser.add_argument("--prompt-source", dest="prompt_source", default="synthetic")
    parser.add_argument("--prompt-len", dest="prompt_len", default="true")
    parser.add_argument("--image-resolution", dest="image_resolution", default="64")
    parser.add_argument("--batch-size", dest="batch_size", default="true")
    parser.add_argument("--num-images", dest="num_images", default="1")
    parser.add_argument("--num-inference-steps", dest="num_inference_steps", default="2")
    parser.add_argument("--guidance-scale", dest="guidance_scale", default="0.0")
    parser.add_argument("--seed", default="42")
    parser.add_argument("--device-id", dest="device_id", default="0")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("HF_HOME", str(repo_root / ".cache" / "huggingface"))

    backend = str(args.backend).strip().lower()
    if not backend:
        backend = "sdxl"
    if backend not in {"tiny", "sdxl"}:
        raise SystemExit(f"[FAIL] backend must be tiny or sdxl; got {args.backend}")

    if not torch.cuda.is_available():
        raise SystemExit("[FAIL] torch.cuda.is_available() is False")
    device = torch.device(f"cuda:{int(float(args.device_id))}")
    torch.cuda.set_device(device)
    dtype = resolve_dtype(str(args.precision))
    if str(args.scheduler).strip().lower() != "euler":
        raise SystemExit("[FAIL] scheduler must remain euler.")
    if str(args.prompt_source).strip().lower() != "synthetic":
        raise SystemExit("[FAIL] prompt_source must remain synthetic.")

    resolution = max(8, int(float(args.image_resolution)))
    steps = max(1, int(float(args.num_inference_steps)))
    num_images = max(1, int(float(args.num_images)))
    if backend == "sdxl":
        resolution = max(MIN_REAL_RESOLUTION, resolution)
        steps = max(2, steps)
        num_images = max(MIN_TIMED_IMAGES, num_images)
    batch_size = effective_int(args.batch_size, 1)
    prompt_len = yaml_token(args.prompt_len)
    guidance_scale = float(yaml_token(args.guidance_scale))
    seed = int(float(args.seed))

    print(f"# SDXL backend={backend}")
    print(f"# model_name={args.model_name}")
    print(f"# precision={args.precision}")
    print(f"# scheduler={args.scheduler}")
    print(f"# prompt_source={args.prompt_source}")
    print(f"# image_resolution={resolution}")
    print(f"# num_images={num_images}")
    print(f"# num_inference_steps={steps}")
    print(f"# guidance_scale={guidance_scale}")
    print(f"# seed={seed}")

    if backend == "tiny":
        rows, metrics = run_tiny(device, dtype, resolution, steps, num_images, seed)
    else:
        rows, metrics = run_sdxl(
            device,
            dtype,
            resolve_hf_id(str(args.model_name)),
            str(args.scheduler),
            sized_prompt(prompt_len),
            resolution,
            steps,
            num_images,
            batch_size,
            guidance_scale,
            seed,
        )
        if metrics["peak_vram_gb"] < MIN_SDXL_VRAM_GB:
            raise SystemExit(
                f"[FAIL] real SDXL peak VRAM {metrics['peak_vram_gb']:.3f} GB is below "
                f"{MIN_SDXL_VRAM_GB:.1f} GB; refusing stand-in metrics"
            )

    params = {
        "model_name": args.model_name,
        "precision": args.precision,
        "scheduler": args.scheduler,
        "prompt_source": args.prompt_source,
        "prompt_len": prompt_len,
        "image_resolution": resolution,
        "batch_size": yaml_token(args.batch_size),
        "num_images": num_images,
        "num_inference_steps": steps,
        "guidance_scale": yaml_token(args.guidance_scale),
        "seed": seed,
    }
    write_csv(Path(args.output) if args.output else None, rows)
    print(
        "sdxl "
        f"per_image_latency_sec={metrics['per_image_latency_sec']:.6f} "
        f"images_per_sec={metrics['images_per_sec']:.6f} "
        f"peak_vram_gb={metrics['peak_vram_gb']:.6f}"
    )
    print(
        result_line(
            params,
            {
                "per_image_latency_sec": metrics["per_image_latency_sec"],
                "images_per_sec": metrics["images_per_sec"],
                "peak_vram_gb": metrics["peak_vram_gb"],
                "first_image_latency_sec": metrics["first_image_latency_sec"],
                "step_time_ms": metrics["step_time_ms"],
            },
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
