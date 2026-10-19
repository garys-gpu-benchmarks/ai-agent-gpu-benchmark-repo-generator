#!/usr/bin/env python3
"""ResNet-50 BF16 inference throughput sweep on synthetic images."""

from __future__ import annotations

import argparse
import math
import time
import subprocess
import threading

import torch
import torchvision.models


def finite_nonneg(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        return 0.0
    return parsed


def parse_batches(text: str) -> list[int]:
    return [max(1, int(float(item))) for item in str(text).split(",") if item.strip()]


def gpu_util(device_id: int) -> float | None:
    """One nvidia-smi utilization.gpu reading; None when it gives none
    (it used to return 0.0, which read as a real idle GPU)."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--id={device_id}",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
        value = float(completed.stdout.strip().splitlines()[0])
    except (IndexError, ValueError, OSError, subprocess.TimeoutExpired):
        return None
    return value if math.isfinite(value) and value >= 0.0 else None


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


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(math.ceil(q * len(ordered)) - 1)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-id", default="0")
    parser.add_argument("--weights", default="random")
    parser.add_argument("--dtype", default="bf16")
    parser.add_argument("--precision", default="bf16")
    parser.add_argument("--image-source", default="synthetic")
    parser.add_argument("--image-size", default="64")
    parser.add_argument("--use-channels-last", default="true")
    parser.add_argument("--batch-size", default="1,2")
    parser.add_argument("--num-workers", default="0")
    parser.add_argument("--warmup-iters", default="1")
    parser.add_argument("--num-iterations", default="3")
    args = parser.parse_args()
    if str(args.image_source).strip().lower() != "synthetic":
        raise SystemExit("[FAIL] image_source must remain synthetic.")
    if not torch.cuda.is_available():
        raise SystemExit("[FAIL] torch.cuda.is_available() is False")
    device = torch.device(f"cuda:{int(args.device_id)}")
    torch.cuda.set_device(device)
    image_size = max(1, int(float(args.image_size)))
    warmup = max(0, int(float(args.warmup_iters)))
    iters = max(1, int(float(args.num_iterations)))
    dtype = torch.bfloat16
    model = torchvision.models.resnet50(weights=None)
    model.eval()
    model.to(device=device, dtype=dtype)
    if str(args.use_channels_last).strip().lower() in {"true", "1", "yes", "on"}:
        model = model.to(memory_format=torch.channels_last)
    for batch in parse_batches(args.batch_size):
        images = torch.randn(batch, 3, image_size, image_size, device=device, dtype=dtype)
        if str(args.use_channels_last).strip().lower() in {"true", "1", "yes", "on"}:
            images = images.to(memory_format=torch.channels_last)
        for _ in range(warmup):
            model(images)
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
        times_ms: list[float] = []
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        loop_start = time.perf_counter()
        with UtilSampler(lambda: gpu_util(int(args.device_id)), "nvidia-smi") as sampler:
            while True:
                start.record()
                model(images)
                end.record()
                torch.cuda.synchronize(device)
                times_ms.append(float(start.elapsed_time(end)))
                if len(times_ms) >= iters and (time.perf_counter() - loop_start) >= 1.0:
                    break
                if len(times_ms) >= max(iters, 200):
                    break
        util = sampler.result()
        mean_ms = sum(times_ms) / len(times_ms)
        images_per_sec = finite_nonneg(float(batch) / (mean_ms / 1000.0))
        per_image = finite_nonneg(mean_ms / float(batch))
        latency_max = finite_nonneg(max(times_ms))
        p99 = finite_nonneg(percentile(times_ms, 0.99))
        p99_text = f"{p99:.6f}" if len(times_ms) >= 100 else "na"
        peak = finite_nonneg(float(torch.cuda.max_memory_allocated(device)) / 1e9)
        # "na" keeps the RESULT line one token per field; the reason follows on
        # its own UTIL_NA line for collect_resnet50_infer.py.
        util_text = f"{util:.6f}" if isinstance(util, float) else "na"
        if not isinstance(util, float):
            print(f"UTIL_NA batch_size={batch} reason={util}")
        if len(times_ms) < 100:
            print(
                f"PERCENTILE_NA batch_size={batch} "
                f"reason=na (p99 requires at least 100 samples; n={len(times_ms)})"
            )
        print(
            "RESULT"
            f" dtype={args.dtype}"
            f" precision={args.precision}"
            f" image_size={image_size}"
            f" batch_size={batch}"
            f" images_per_sec={images_per_sec:.6f}"
            f" per_image_latency_msec={per_image:.6f}"
            f" batch_latency_max_msec={latency_max:.6f}"
            f" latency_sample_count={len(times_ms)}"
            f" batch_p99_latency_msec={p99_text}"
            f" gpu_utilization_percent={util_text}"
            f" peak_gpu_memory_gb={peak:.6f}"
            " status=ok"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
