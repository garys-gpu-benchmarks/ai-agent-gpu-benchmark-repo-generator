#!/usr/bin/env python3
# File: scripts/collect_sdxl.py
# Description: Run real SDXL once and emit METRICS_CSV with one timed sample plus summary.
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path
from statistics import mean

import yaml


MIN_REAL_RESOLUTION = 256
MIN_TIMED_IMAGES = 2


METRIC_FIELDS = [
    "per_image_latency_sec",
    "images_per_sec",
    "peak_vram_gb",
    "step_time_ms",
    "first_image_latency_s",
]
PARAM_FIELDS = [
    "model_name",
    "precision",
    "scheduler",
    "prompt_source",
    "prompt_len",
    "image_resolution",
    "batch_size",
    "num_images",
    "num_inference_steps",
    "guidance_scale",
    "seed",
]
RESULT_RE = re.compile(
    r"RESULT\s+"
    r"model_name=(\S+)\s+precision=(\S+)\s+scheduler=(\S+)\s+"
    r"prompt_source=(\S+)\s+prompt_len=(\S+)\s+image_resolution=(\S+)\s+"
    r"batch_size=(\S+)\s+num_images=(\S+)\s+num_inference_steps=(\S+)\s+"
    r"guidance_scale=(\S+)\s+seed=(\S+)\s+"
    r"per_image_latency_sec=([0-9.eE+-]+)\s+images_per_sec=([0-9.eE+-]+)\s+"
    r"peak_vram_gb=([0-9.eE+-]+)\s+"
    r"first_image_latency_sec=([0-9.eE+-]+)\s+step_time_ms=([0-9.eE+-]+)\s+"
    r"status=(\w+)"
)


def yaml_token(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    if text.lower() == "true":
        return "true"
    if text.lower() == "false":
        return "false"
    return text


def profile_value(sweep: dict, key: str, profile: str, default):
    value = sweep.get(key, default)
    if isinstance(value, dict):
        if profile in value:
            return value[profile]
        if "smoke" in value:
            return value["smoke"]
    return value


def load_sweep(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload.get("sweep", payload)


def parse_results(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for match in RESULT_RE.finditer(text):
        rows.append(
            {
                "model_name": match.group(1),
                "precision": match.group(2),
                "scheduler": match.group(3),
                "prompt_source": match.group(4),
                "prompt_len": match.group(5),
                "image_resolution": match.group(6),
                "batch_size": match.group(7),
                "num_images": match.group(8),
                "num_inference_steps": match.group(9),
                "guidance_scale": match.group(10),
                "seed": match.group(11),
                "per_image_latency_sec": float(match.group(12)),
                "images_per_sec": float(match.group(13)),
                "peak_vram_gb": float(match.group(14)),
                "first_image_latency_s": float(match.group(15)),
                "step_time_ms": float(match.group(16)),
                "status": match.group(17),
            }
        )
    if not rows:
        raise SystemExit("[FAIL] No RESULT line was parsed from infer_sdxl.py.")
    return rows


def run_text(command: list[str], timeout: int) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


def estimate_timeout(backend: str, steps: int, images: int) -> int:
    if backend == "tiny":
        return max(300, int(max(steps, 1) * max(images, 1) * 0.003) + 180)
    return max(1800, int(max(steps, 1) * max(images, 1) * 15) + 300)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect SDXL inference samples")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--backend", default="")
    parser.add_argument("--model-name", dest="model_name", default="")
    parser.add_argument("--precision", default="")
    parser.add_argument("--scheduler", default="")
    parser.add_argument("--prompt-source", dest="prompt_source", default="")
    parser.add_argument("--prompt-len", dest="prompt_len", default="")
    parser.add_argument("--image-resolution", dest="image_resolution", default="")
    parser.add_argument("--batch-size", dest="batch_size", default="")
    parser.add_argument("--num-images", dest="num_images", default="")
    parser.add_argument("--num-inference-steps", dest="num_inference_steps", default="")
    parser.add_argument("--guidance-scale", dest="guidance_scale", default="")
    parser.add_argument("--seed", default="")
    args = parser.parse_args()

    sweep = load_sweep(Path(args.config))
    profile = args.profile
    backend = str(args.backend).strip().lower()
    if not backend:
        backend = "sdxl"
    if backend != "sdxl":
        raise SystemExit("[FAIL] TinyDenoiser is a setup self-test and cannot publish SDXL metrics.")
    model_name = yaml_token(args.model_name or profile_value(sweep, "model_name", profile, "sdxl-base-1.0"))
    precision = yaml_token(args.precision or profile_value(sweep, "precision", profile, "fp16"))
    scheduler = yaml_token(args.scheduler or profile_value(sweep, "scheduler", profile, "euler"))
    prompt_source = yaml_token(args.prompt_source or profile_value(sweep, "prompt_source", profile, "synthetic"))
    prompt_len = yaml_token(args.prompt_len or profile_value(sweep, "prompt_len", profile, True))
    image_resolution = str(max(
        MIN_REAL_RESOLUTION,
        int(float(args.image_resolution or profile_value(sweep, "image_resolution", profile, MIN_REAL_RESOLUTION))),
    ))
    batch_size = yaml_token(args.batch_size or profile_value(sweep, "batch_size", profile, True))
    num_images = str(max(
        MIN_TIMED_IMAGES,
        int(float(args.num_images or profile_value(sweep, "num_images", profile, MIN_TIMED_IMAGES))),
    ))
    num_inference_steps = str(max(
        2,
        int(float(args.num_inference_steps or profile_value(sweep, "num_inference_steps", profile, 2))),
    ))
    guidance_scale = yaml_token(args.guidance_scale or profile_value(sweep, "guidance_scale", profile, "0.0"))
    seed = yaml_token(args.seed or profile_value(sweep, "seed", profile, 42))

    python_bin = sys.executable
    repo_root = Path(__file__).resolve().parent.parent
    infer_script = str(repo_root / "scripts" / "infer_sdxl.py")
    timeout_sec = estimate_timeout(backend, int(float(num_inference_steps)), int(float(num_images)))

    print(f"# NVIDIA SDXL inference raw transcript backend={backend}")
    print(f"# profile={profile}")
    print(f"# model_name={model_name}")
    print(f"# precision={precision}")
    print(f"# scheduler={scheduler}")
    print(f"# prompt_source={prompt_source}")
    print(f"# prompt_len={prompt_len}")
    print(f"# image_resolution={image_resolution}")
    print(f"# batch_size={batch_size}")
    print(f"# num_images={num_images}")
    print(f"# num_inference_steps={num_inference_steps}")
    print(f"# guidance_scale={guidance_scale}")
    print(f"# seed={seed}")

    shared_params = {
        "model_name": model_name,
        "precision": precision,
        "scheduler": scheduler,
        "prompt_source": prompt_source,
        "prompt_len": prompt_len,
        "image_resolution": image_resolution,
        "batch_size": batch_size,
        "num_images": num_images,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
        "seed": seed,
    }
    rows: list[dict[str, object]] = []
    for pass_index in (1,):  # one timed pass
        print(f"# timed_pass={pass_index}")
        command = [
            python_bin,
            infer_script,
            "--backend",
            backend,
            "--profile",
            profile,
            "--model-name",
            model_name,
            "--precision",
            precision,
            "--scheduler",
            scheduler,
            "--prompt-source",
            prompt_source,
            "--prompt-len",
            prompt_len,
            "--image-resolution",
            image_resolution,
            "--batch-size",
            batch_size,
            "--num-images",
            num_images,
            "--num-inference-steps",
            num_inference_steps,
            "--guidance-scale",
            guidance_scale,
            "--seed",
            seed,
        ]
        code, text = run_text(command, timeout=timeout_sec)
        print(f"# check=infer-pass{pass_index} exit={code}")
        print(text.rstrip())
        print()
        if code != 0:
            raise SystemExit(f"[FAIL] infer_sdxl.py exited {code} on pass {pass_index}")
        for parsed in parse_results(text):
            status = str(parsed.get("status", "ok")).lower()
            if status not in {"ok", "pass", "passed"}:
                status = "error"
            rows.append(
                {
                    "check": f"pass{pass_index}",
                    "status": status,
                    **shared_params,
                    "per_image_latency_sec": float(parsed["per_image_latency_sec"]),
                    "images_per_sec": float(parsed["images_per_sec"]),
                    "peak_vram_gb": float(parsed["peak_vram_gb"]),
                    "step_time_ms": float(parsed["step_time_ms"]),
                    "first_image_latency_s": float(parsed["first_image_latency_s"]),
                }
            )

    if len(rows) < 1:
        raise SystemExit("[FAIL] Collector must emit at least one timed sample.")

    total_images = sum(int(float(row["num_images"])) for row in rows)
    total_timed_seconds = sum(
        int(float(row["num_images"])) * float(row["per_image_latency_sec"]) for row in rows
    )
    summary = {
        "check": "summary",
        "status": "ok",
        **shared_params,
        "per_image_latency_sec": mean(float(row["per_image_latency_sec"]) for row in rows),
        "images_per_sec": total_images / total_timed_seconds,
        "peak_vram_gb": max(float(row["peak_vram_gb"]) for row in rows),
        "step_time_ms": mean(float(row["step_time_ms"]) for row in rows),
        "first_image_latency_s": mean(float(row["first_image_latency_s"]) for row in rows),
    }
    rows.append(summary)

    fieldnames = ["check", "status", *PARAM_FIELDS, *METRIC_FIELDS]
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print("# METRICS_CSV")
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    with output_path.open(encoding="utf-8") as handle:
        print(handle.read(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
