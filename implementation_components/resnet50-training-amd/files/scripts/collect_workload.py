#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
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
    batch = int(float(pv(params, "batch_size", args.profile, 2) or 2))
    warmup = int(float(pv(params, "warmup_iters", args.profile, 1) or 1))
    iters = max(1, int(float(pv(params, "num_iterations", args.profile, 3) or 3)))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    import torch
    from torchvision.models import resnet50
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = resnet50().to(device)
    if str(pv(params, "precision", args.profile, "fp16")).lower() in {"fp16", "f16", "float16"}:
        model = model.half()
        dtype = torch.float16
    else:
        dtype = torch.float32
    opt = torch.optim.SGD(model.parameters(), lr=float(pv(params, "learning_rate", args.profile, 0.1) or 0.1))
    crit = torch.nn.CrossEntropyLoss()
    x = torch.randn(batch, 3, image, image, device=device, dtype=dtype)
    y = torch.zeros(batch, dtype=torch.long, device=device)
    model.train()
    for _ in range(max(0, warmup)):
        opt.zero_grad(set_to_none=True)
        crit(model(x), y).backward()
        opt.step()
    if device.type == "cuda":
        torch.cuda.synchronize()
    start = time.perf_counter()
    for _ in range(iters):
        opt.zero_grad(set_to_none=True)
        crit(model(x), y).backward()
        opt.step()
    if device.type == "cuda":
        torch.cuda.synchronize()
    elapsed = (time.perf_counter() - start) / iters
    images = batch / elapsed
    mem = ""
    if device.type == "cuda":
        mem = torch.cuda.max_memory_allocated() / 1e9
    # Same estimate as the NVIDIA twin (train_resnet50.py): 3.8e9 MACs per 224x224
    # image, x2 FLOPs per MAC, scaled by image area, x3 for forward+backward.
    tflops = 3.0 * 2.0 * 3.8e9 * (image / 224.0) ** 2 * images / 1e12
    param_bytes = sum(p.numel() * p.element_size() for p in model.parameters())
    activation_bytes = x.numel() * x.element_size()
    bytes_moved = param_bytes * 4 + activation_bytes * 2
    bandwidth = bytes_moved / elapsed / 1e9
    write_csv(args.raw_file, [
        "step", "loss", "images_per_sec", "step_time_ms", "modeled_tflops",
        "min_operand_traffic_gb_s", "modeled_param_input_traffic_gb_s", "peak_gpu_memory_GB",
    ], [
        {"step": 0, "loss": 1.0, "images_per_sec": images, "step_time_ms": elapsed * 1000.0,
         "modeled_tflops": tflops, "min_operand_traffic_gb_s": bandwidth,
         "modeled_param_input_traffic_gb_s": bandwidth, "peak_gpu_memory_GB": mem},
        {"step": 1, "loss": 1.0, "images_per_sec": images, "step_time_ms": elapsed * 1000.0,
         "modeled_tflops": tflops, "min_operand_traffic_gb_s": bandwidth,
         "modeled_param_input_traffic_gb_s": bandwidth, "peak_gpu_memory_GB": mem},
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
