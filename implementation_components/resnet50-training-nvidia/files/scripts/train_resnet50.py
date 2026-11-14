#!/usr/bin/env python3
# File: scripts/train_resnet50.py
# Version: 1.0.0
# Author: TEMPLATE_00_54 generator
# Date: 2026-08-19
# Description: Time one ResNet-50 FP16 training step on synthetic NCHW tensors.
# Execution: .venv/bin/python scripts/train_resnet50.py --image-size 64 --batch-size 2 --warmup-iters 1 --num-iterations 3
# Options: --dataset-name, --precision, --image-size, --batch-size, --num-workers, --optimizer, --learning-rate, --gradient-accumulation, --warmup-iters, --num-iterations, --device-id
# Requirements: Python 3.12, PyTorch-CUDA, torchvision
# Environment: Repository-local .venv after setup.sh
# Dependencies: torch, torchvision
# Variables: none
# Repository: gpu-bench-nvidia-resnet50-pytorch-training
# License: Apache-2.0

from __future__ import annotations

import argparse
import math

import torch
import torchvision.models


# He et al., Deep Residual Learning for Image Recognition (CVPR 2016), Table 1:
# ResNet-50 is listed as 3.8 x 10^9 FLOPs. Those published figures are
# multiply-adds (MACs) at 224x224. Convert MACs to FLOPs with 2x. Spatial
# convolution work scales as (image_size / 224)^2. A training step is
# approximated as 3x inference (forward + backward + parameter update).
RESNET50_INFERENCE_MACS_224 = 3.8e9
# torchvision ResNet-50 parameter count (weights=None, 1000 classes).
RESNET50_PARAM_COUNT = 25_557_032
IMAGENET_CLASSES = 1000


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


def finite_nonneg(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        return 0.0
    return parsed


def token_is_enabled(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "on", "sgd"}


def dataloader_workers(value: object) -> int:
    # yaml token true means the DataLoader worker path is enabled; the
    # implementation uses 0 workers and does not invent a yaml worker count.
    text = str(value).strip().lower()
    if token_is_enabled(text):
        return 0
    if text in {"false", "0", "no", "off", ""}:
        return 0
    return max(0, int(float(text)))


def accumulation_steps(value: object) -> int:
    # yaml token true is an enabled flag. Keep the token and use 1 step.
    text = str(value).strip().lower()
    if token_is_enabled(text):
        return 1
    if text in {"false", "0", "no", "off", ""}:
        return 1
    return max(1, int(float(text)))


def training_flops(batch_size: int, image_size: int) -> float:
    scale = (float(image_size) / 224.0) ** 2
    inference_flops = 2.0 * RESNET50_INFERENCE_MACS_224 * scale
    return 3.0 * inference_flops * float(batch_size)


def bytes_moved_per_step(batch_size: int, image_size: int) -> float:
    # Approximate traffic: FP16 weight read (fwd), FP16 weight read (bwd),
    # FP16 gradient write, plus SGD FP32 master read/write. Activations use
    # a conservative 16x input-volume factor for ResNet-50 feature maps.
    weight_bytes = float(RESNET50_PARAM_COUNT) * (2.0 + 2.0 + 2.0 + 4.0 + 4.0)
    activation_bytes = float(batch_size) * 3.0 * float(image_size) * float(image_size) * 2.0 * 16.0
    return weight_bytes + activation_bytes


class SyntheticClassification(torch.utils.data.Dataset):
    def __init__(self, length: int, image_size: int) -> None:
        self.length = max(1, int(length))
        self.image_size = int(image_size)

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        del index
        image = torch.randn(3, self.image_size, self.image_size)
        label = int(torch.randint(0, IMAGENET_CLASSES, (1,)).item())
        return image, label


def main() -> int:
    parser = argparse.ArgumentParser(description="Time a ResNet-50 FP16 training step")
    parser.add_argument("--dataset-name", dest="dataset_name", default="synthetic")
    parser.add_argument("--precision", default="fp16")
    parser.add_argument("--image-size", dest="image_size", default="64")
    parser.add_argument("--batch-size", dest="batch_size", default="2")
    parser.add_argument("--num-workers", dest="num_workers", default="true")
    parser.add_argument("--optimizer", default="true")
    parser.add_argument("--learning-rate", dest="learning_rate", default="0.1")
    parser.add_argument("--gradient-accumulation", dest="gradient_accumulation", default="true")
    parser.add_argument("--warmup-iters", dest="warmup_iters", default="1")
    parser.add_argument("--num-iterations", dest="num_iterations", default="3")
    parser.add_argument("--device-id", dest="device_id", default="0")
    args = parser.parse_args()

    if str(args.dataset_name).strip().lower() != "synthetic":
        raise SystemExit(
            "[FAIL] dataset_name must remain synthetic; ImageNet download is not used."
        )
    if str(args.precision).strip().lower() not in {"fp16", "f16", "f16_r", "half"}:
        raise SystemExit(f"[FAIL] This workload times FP16 only; got precision={args.precision}")
    if not torch.cuda.is_available():
        raise SystemExit("[FAIL] torch.cuda.is_available() is False")

    device = torch.device(f"cuda:{int(args.device_id)}")
    torch.cuda.set_device(device)
    image_size = max(1, int(float(args.image_size)))
    batch_size = max(1, int(float(args.batch_size)))
    warmup_iters = max(0, int(float(args.warmup_iters)))
    num_iterations = max(1, int(float(args.num_iterations)))
    workers = dataloader_workers(args.num_workers)
    accum_steps = accumulation_steps(args.gradient_accumulation)
    learning_rate = float(args.learning_rate)
    if not token_is_enabled(args.optimizer):
        raise SystemExit("[FAIL] optimizer token must be true so SGD is used")

    # weights=None keeps the randomly initialized model; do not download pretrained weights.
    model = torchvision.models.resnet50(weights=None)
    model.train()
    model.to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=learning_rate)
    criterion = torch.nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler("cuda")

    # Recycle a small synthetic pool. Materializing one batch per iteration
    # (13200 * 8 or 37400 * 16 images at 224) OOMs the host and SIGKILLs the trainer.
    pool = batch_size * 4
    dataset = SyntheticClassification(pool, image_size)
    loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
        drop_last=True,
    )
    batches = list(loader)
    if not batches:
        raise SystemExit("[FAIL] Synthetic DataLoader produced no batches")

    torch.cuda.reset_peak_memory_stats(device)
    total_steps = warmup_iters + num_iterations
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    timed_started = False

    for step in range(total_steps):
        images, labels = batches[step % len(batches)]
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        if step == warmup_iters:
            torch.cuda.synchronize(device)
            mark_measure_start()  # setup ends: model loaded, warmup done
            start.record()
            timed_started = True
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast("cuda", dtype=torch.float16):
            logits = model(images)
            loss = criterion(logits, labels) / float(accum_steps)
        scaler.scale(loss).backward()
        if (step + 1) % accum_steps == 0:
            scaler.step(optimizer)
            scaler.update()

    if timed_started:
        end.record()
        torch.cuda.synchronize(device)
        elapsed_ms = float(start.elapsed_time(end))
    else:
        elapsed_ms = 0.0

    step_time_msec = finite_nonneg(elapsed_ms / float(num_iterations))
    time_sec = step_time_msec / 1000.0
    if time_sec <= 0.0:
        images_per_sec = 0.0
        fp16_tflops = 0.0
        memory_bandwidth_gb_s = 0.0
    else:
        images_per_sec = finite_nonneg(float(batch_size) / time_sec)
        fp16_tflops = finite_nonneg(training_flops(batch_size, image_size) / time_sec / 1e12)
        memory_bandwidth_gb_s = finite_nonneg(
            bytes_moved_per_step(batch_size, image_size) / time_sec / 1e9
        )
    peak_gpu_memory_gb = finite_nonneg(float(torch.cuda.max_memory_allocated(device)) / 1e9)

    print(
        f"resnet50 step_time_msec={step_time_msec:.6f} "
        f"images_per_sec={images_per_sec:.6f} "
        f"fp16_tflops={fp16_tflops:.6f} "
        f"memory_bandwidth_gb_s={memory_bandwidth_gb_s:.6f} "
        f"peak_gpu_memory_gb={peak_gpu_memory_gb:.6f}"
    )
    print(
        "RESULT"
        f" dataset_name={args.dataset_name}"
        f" precision={args.precision}"
        f" image_size={image_size}"
        f" batch_size={batch_size}"
        f" num_workers={args.num_workers}"
        f" optimizer={args.optimizer}"
        f" learning_rate={args.learning_rate}"
        f" gradient_accumulation={args.gradient_accumulation}"
        f" warmup_iters={warmup_iters}"
        f" num_iterations={num_iterations}"
        f" step_time_msec={step_time_msec:.6f}"
        f" images_per_sec={images_per_sec:.6f}"
        f" fp16_tflops={fp16_tflops:.6f}"
        f" memory_bandwidth_gb_s={memory_bandwidth_gb_s:.6f}"
        f" peak_gpu_memory_gb={peak_gpu_memory_gb:.6f}"
        " status=ok"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
