#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import math
import subprocess
import threading
import time
from pathlib import Path

import yaml


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def as_list(value):
    return [p.strip() for p in str(value or "").replace(";", ",").split(",") if p.strip()]


def duration_seconds(raw):
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return 5.0
    return number / 1000.0 if number >= 10000 else number


def load_params(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return cfg.get("sweep") or {}


def write_csv(path, header, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    rows = list(rows)
    if len(rows) == 1:
        rows.append(dict(rows[0]))
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    text = buf.getvalue()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    print(text, end="")
    return text



def read_amd_gpu_util() -> float | None:
    """GPU busy percent. amdgpu sysfs (instant, no subprocess) first, the
    highest across AMD cards; amd-smi as a fallback."""
    values = []
    for path in Path("/sys/class/drm").glob("card[0-9]*/device/gpu_busy_percent"):
        try:
            vendor = (path.parent / "vendor").read_text().strip()
            if vendor != "0x1002":
                continue
            values.append(float(path.read_text().strip()))
        except (OSError, ValueError):
            continue
    if values:
        return max(values)
    for cmd in (
        ["amd-smi", "metric", "--usage"],
    ):
        try:
            probe = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in ((probe.stdout or "") + (probe.stderr or "")).splitlines():
            compact = line.lower().replace(" ", "").replace("_", "")
            if "gfxactivity" not in compact and "gpuuse" not in compact:
                continue
            nums = [
                float(tok)
                for tok in line.replace("%", " ").replace(":", " ").replace("_", " ").split()
                if tok.replace(".", "", 1).isdigit()
            ]
            if nums:
                return nums[0]
    return None


class UtilSampler:
    """Reads GPU utilization on a background thread while the timed loop runs.

    Utilization used to be read once after the loop had finished and
    synchronized, so it reported an idle GPU (about 0%). A reading counts only
    if the call finished before the loop ended, so it describes the loop.
    result() is the mean of those readings, or an "na (<reason>)" text."""

    def __init__(self, read, tool: str, interval: float = 0.1):
        self._read = read
        self._tool = tool
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.values: list[float] = []
        self.failed = 0

    def _run(self) -> None:
        while not self._stop.is_set():
            value = self._read()
            if self._stop.is_set():
                break  # finished after the loop ended: not a reading of the loop
            if value is None:
                self.failed += 1
            else:
                self.values.append(value)
            self._stop.wait(self._interval)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        self._thread.join(timeout=30)

    def result(self):
        if self.values:
            return sum(self.values) / len(self.values)
        if self.failed:
            return f"na ({self._tool} gave no utilization reading)"
        return "na (timed loop too short to sample)"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    image = int(float(pv(params, "image_size", args.profile, 64) or 64))
    warmup = int(float(pv(params, "warmup_iters", args.profile, 1) or 1))
    iters = max(1, int(float(pv(params, "num_iterations", args.profile, 3) or 3)))
    batches = [int(float(x)) for x in as_list(pv(params, "batch_size", args.profile, "1"))]
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    import torch
    from torchvision.models import resnet50
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.bfloat16 if "bf16" in str(pv(params, "dtype", args.profile, "bf16")).lower() else torch.float16
    model = resnet50().to(device=device, dtype=dtype).eval()
    rows = []
    with torch.no_grad():
        for batch in batches:
            x = torch.randn(batch, 3, image, image, device=device, dtype=dtype)
            for _ in range(max(0, warmup)):
                model(x)
            if device.type == "cuda":
                torch.cuda.synchronize()
                # Peak memory per batch size: without a reset every later batch
                # reported the largest peak so far.
                torch.cuda.reset_peak_memory_stats()
            samples = []
            loop_start = time.perf_counter()
            with UtilSampler(read_amd_gpu_util, "amd-smi") as sampler:
                while True:
                    step_start = time.perf_counter()
                    model(x)
                    if device.type == "cuda":
                        torch.cuda.synchronize()
                    samples.append((time.perf_counter() - step_start) * 1000.0)
                    if len(samples) >= iters and (time.perf_counter() - loop_start) >= 1.0:
                        break
                    if len(samples) >= max(iters, 200):
                        break
            util = sampler.result()
            if (
                isinstance(util, str)
                and "too short" in util
                and args.profile == "smoke"
            ):
                util = "na (expected: timed loop shorter than 1s on smoke)"
            mean_ms = sum(samples) / len(samples)
            ordered = sorted(samples)
            p99_index = min(len(ordered) - 1, max(0, math.ceil(0.99 * len(ordered)) - 1))
            p99 = ordered[p99_index]
            latency_max = ordered[-1]
            p99_value = p99 if len(samples) >= 100 else f"na (p99 requires at least 100 samples; n={len(samples)})"
            elapsed = mean_ms / 1000.0
            mem = ""
            if device.type == "cuda":
                mem = torch.cuda.max_memory_allocated() / 1e9
            rows.append({
                "batch_size": batch,
                "batch_latency_max_msec": latency_max,
                "latency_sample_count": len(samples),
                "batch_p99_latency_msec": p99_value,
                "per_image_latency_ms": mean_ms / batch,
                "images_sec": batch / elapsed if elapsed else "",
                "gpu_util_percent": util,
                "peak_gpu_memory_GB": mem,
            })
    metric_columns = [
        "batch_latency_max_msec", "batch_p99_latency_msec", "per_image_latency_ms", "images_sec",
        "gpu_util_percent", "peak_gpu_memory_GB",
    ]
    headline = max(rows, key=lambda row: row["batch_size"])
    for row in rows:
        row["headline_batch_size"] = headline["batch_size"]
        for key in metric_columns:
            row[f"case_{key}"] = row[key]
            row[key] = headline[key]
    write_csv(args.raw_file, [
        "batch_size", "batch_latency_max_msec", "latency_sample_count", "batch_p99_latency_msec",
        "per_image_latency_ms", "images_sec", "gpu_util_percent", "peak_gpu_memory_GB",
        "headline_batch_size", *[f"case_{key}" for key in metric_columns],
    ], rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
