#!/usr/bin/env python3
# File: scripts/collect_cudnn_conv.py
# Version: 1.1.0
# Author: TEMPLATE_00_54 generator
# Date: 2026-09-29
# Description: Run the cuDNN convolution harness twice and emit METRICS_CSV samples plus summary.
# Execution: .venv/bin/python scripts/collect_cudnn_conv.py --output PATH --config PATH
# Options: --output, --config, --profile, --dtype, --input-source, --conv-direction, --batch-size, --input-channels, --input-height, --input-width, --output-channels, --kernel-height, --kernel-width, --stride-h, --stride-w, --group-count, --search-strategy, --warmup-iters, --num-iterations, --harness
# Requirements: Python 3.12, PyYAML
# Environment: Repository-local .venv after setup.sh
# Dependencies: bin/cudnn_conv
# Variables: PATH
# Repository: gpu-bench-nvidia-cudnn-convolution-micro
# License: Apache-2.0

from __future__ import annotations

import argparse
import csv
import math
import os
import subprocess
from pathlib import Path
from statistics import mean

import yaml


METRIC_FIELDS = [
    "kernel_time_msec",
    "tflops_fwd",
    "tflops_bwd_data",
    "tflops_bwd_weights",
    "solver_search_msec",
    "memory_bandwidth_gb_s",
    "kernel_time_msec_bwd_data",
    "kernel_time_msec_bwd_weights",
    "memory_bandwidth_gb_s_bwd_data",
    "memory_bandwidth_gb_s_bwd_weights",
    "algo_fwd",
    "algo_bwd_data",
    "algo_bwd_weights",
]
PARAM_FIELDS = [
    "dtype",
    "input_source",
    "conv_direction",
    "batch_size",
    "input_channels",
    "input_height",
    "input_width",
    "output_channels",
    "kernel_height",
    "kernel_width",
    "stride_h",
    "stride_w",
    "group_count",
    "search_strategy",
    "warmup_iters",
    "num_iterations",
    "pad_h",
    "pad_w",
    "dtype_effective",
]


def _tensor_ir_preload() -> str | None:
    """Return /opt/cudnn-host-extra only when that directory holds tensor_ir.

    An empty directory is not a library. Skip the preload when this repo's
    virtualenv already ships libcudnn_engines_tensor_ir.so.9 so a moved system
    copy is not mixed with the venv cuDNN.
    """
    repo = Path(__file__).resolve().parents[1]
    venv_engine = list(
        repo.glob(".venv/lib/python*/site-packages/nvidia/cudnn/lib/libcudnn_engines_tensor_ir.so.9")
    )
    if any(path.is_file() or path.is_symlink() for path in venv_engine):
        return None
    extra = Path("/opt/cudnn-host-extra")
    for name in ("libcudnn_engines_tensor_ir.so.9", "libcudnn_engines_tensor_ir.so"):
        path = extra / name
        if path.is_file() or path.is_symlink():
            return str(extra)
    return None


def run_text(command: list[str], timeout: int) -> tuple[int, str]:
    try:
        env = os.environ.copy()
        extra = _tensor_ir_preload()
        if extra:
            current = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = extra + (f":{current}" if current else "")
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=env,
        )
        return completed.returncode, completed.stdout
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


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


def requested_directions(conv_direction: str) -> list[str]:
    key = str(conv_direction or "").strip().lower()
    if key == "all":
        return ["fwd", "bwd_data", "bwd_weights"]
    if key in {"fwd", "forward"}:
        return ["fwd"]
    if key in {"bwd_data", "bwd-data"}:
        return ["bwd_data"]
    if key in {"bwd_weights", "bwd-weights", "bwd_filter", "bwd-filter"}:
        return ["bwd_weights"]
    raise SystemExit(f"[FAIL] unsupported conv_direction {conv_direction}")


def _coerce(value: str):
    if value.lower() in {"nan", "-nan", "+nan"}:
        return None
    try:
        return float(value)
    except ValueError:
        return value


def parse_result_lines(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("RESULT "):
            continue
        item: dict[str, object] = {}
        for token in stripped.split()[1:]:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            item[key] = _coerce(value)
        rows.append(item)
    return rows


def _positive(value: object) -> bool:
    try:
        return float(value) > 0.0
    except (TypeError, ValueError):
        return False


def _csv_number(value: object) -> object:
    if value is None or value == "":
        return ""
    number = float(value)
    if math.isnan(number):
        return ""
    if number.is_integer():
        return int(number)
    return number


def _field(item: dict[str, object] | None, key: str) -> object:
    if not item or key not in item or item[key] is None:
        return ""
    return _csv_number(item[key])


def pass_row(text: str, conv_direction: str, params: dict[str, object], check: str) -> dict[str, object]:
    wanted = requested_directions(conv_direction)
    parsed = parse_result_lines(text)
    by_dir: dict[str, dict[str, object]] = {}
    for item in parsed:
        direction = str(item.get("direction", ""))
        if direction:
            by_dir[direction] = item
    for direction in wanted:
        item = by_dir.get(direction)
        if item is None or not _positive(item.get("kernel_time_msec")):
            raise SystemExit(f"[FAIL] missing RESULT line for direction {direction} on {check}")
        status = str(item.get("status", "ok")).lower()
        if status != "ok":
            raise SystemExit(f"[FAIL] RESULT status for {direction} on {check} is {status}")
    searches = []
    for direction in wanted:
        value = by_dir[direction].get("solver_search_msec")
        if value is None:
            continue
        searches.append(float(value))
    sample = next(iter(by_dir.values()))
    fwd = by_dir.get("fwd")
    bwd_data = by_dir.get("bwd_data")
    bwd_weights = by_dir.get("bwd_weights")
    row: dict[str, object] = {
        "check": check,
        "status": "ok",
        **params,
        "pad_h": _field(sample, "pad_h"),
        "pad_w": _field(sample, "pad_w"),
        "dtype_effective": "" if sample.get("dtype_effective") is None else sample.get("dtype_effective"),
        "kernel_time_msec": _field(fwd, "kernel_time_msec"),
        "tflops_fwd": _field(fwd, "tflops"),
        "memory_bandwidth_gb_s": _field(fwd, "memory_bandwidth_gb_s"),
        "solver_search_msec": sum(searches) if searches else "",
        "tflops_bwd_data": _field(bwd_data, "tflops"),
        "tflops_bwd_weights": _field(bwd_weights, "tflops"),
        "kernel_time_msec_bwd_data": _field(bwd_data, "kernel_time_msec"),
        "kernel_time_msec_bwd_weights": _field(bwd_weights, "kernel_time_msec"),
        "memory_bandwidth_gb_s_bwd_data": _field(bwd_data, "memory_bandwidth_gb_s"),
        "memory_bandwidth_gb_s_bwd_weights": _field(bwd_weights, "memory_bandwidth_gb_s"),
        "algo_fwd": _field(fwd, "algo"),
        "algo_bwd_data": _field(bwd_data, "algo"),
        "algo_bwd_weights": _field(bwd_weights, "algo"),
    }
    return row


def summarize_passes(rows: list[dict[str, object]], params: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {"check": "summary", "status": "ok", **params}
    for key in ("pad_h", "pad_w", "dtype_effective"):
        summary[key] = rows[0].get(key, "")
    for key in METRIC_FIELDS:
        values = [row.get(key, "") for row in rows]
        if any(value == "" or value is None for value in values):
            summary[key] = ""
            continue
        summary[key] = mean(float(value) for value in values)
    return summary


def estimate_timeout(iterations: int, warmup: int, height: int, directions: int = 1) -> int:
    # run_benchmark.sh has no outer timeout. This subprocess budget is the only cap.
    # Historical H100 forward time was about 0.5 ms/iter; 10 ms/iter is allowance,
    # multiplied by the number of directions, plus 120 s for cudnnFind.
    per_iter_ms = 0.05 if height <= 32 else 10.0
    kernel_budget = int((max(iterations, 1) + max(warmup, 0)) * per_iter_ms / 1000.0) * max(directions, 1)
    return max(300, kernel_budget + 180 + 120)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect cuDNN convolution samples")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--dtype", default="")
    parser.add_argument("--input-source", dest="input_source", default="")
    parser.add_argument("--conv-direction", dest="conv_direction", default="")
    parser.add_argument("--batch-size", dest="batch_size", default="")
    parser.add_argument("--input-channels", dest="input_channels", default="")
    parser.add_argument("--input-height", dest="input_height", default="")
    parser.add_argument("--input-width", dest="input_width", default="")
    parser.add_argument("--output-channels", dest="output_channels", default="")
    parser.add_argument("--kernel-height", dest="kernel_height", default="")
    parser.add_argument("--kernel-width", dest="kernel_width", default="")
    parser.add_argument("--stride-h", dest="stride_h", default="")
    parser.add_argument("--stride-w", dest="stride_w", default="")
    parser.add_argument("--group-count", dest="group_count", default="")
    parser.add_argument("--search-strategy", dest="search_strategy", default="")
    parser.add_argument("--warmup-iters", dest="warmup_iters", default="")
    parser.add_argument("--num-iterations", dest="num_iterations", default="")
    parser.add_argument("--harness", default="bin/cudnn_conv")
    args = parser.parse_args()

    sweep = load_sweep(Path(args.config))
    profile = args.profile
    dtype = str(args.dtype or profile_value(sweep, "dtype", profile, "FP16"))
    input_source = str(args.input_source or profile_value(sweep, "input_source", profile, "synthetic"))
    conv_direction = str(args.conv_direction or profile_value(sweep, "conv_direction", profile, "all"))
    batch_size = str(args.batch_size or profile_value(sweep, "batch_size", profile, 1))
    input_channels = str(args.input_channels or profile_value(sweep, "input_channels", profile, 8))
    input_height = str(args.input_height or profile_value(sweep, "input_height", profile, 16))
    input_width = str(args.input_width or profile_value(sweep, "input_width", profile, 16))
    output_channels = str(args.output_channels or profile_value(sweep, "output_channels", profile, 8))
    kernel_height = str(args.kernel_height or profile_value(sweep, "kernel_height", profile, 3))
    kernel_width = str(args.kernel_width or profile_value(sweep, "kernel_width", profile, 3))
    stride_h = str(args.stride_h or profile_value(sweep, "stride_h", profile, 1))
    stride_w = str(args.stride_w or profile_value(sweep, "stride_w", profile, 1))
    group_count = str(args.group_count or profile_value(sweep, "group_count", profile, 1))
    search_strategy = str(args.search_strategy or profile_value(sweep, "search_strategy", profile, "find"))
    warmup_iters = str(args.warmup_iters or profile_value(sweep, "warmup_iters", profile, 1))
    num_iterations = str(args.num_iterations or profile_value(sweep, "num_iterations", profile, 2))
    directions = requested_directions(conv_direction)

    print("# NVIDIA cuDNN convolution raw transcript")
    print(f"# profile={profile}")
    print(f"# dtype={dtype}")
    print(f"# input_source={input_source}")
    print(f"# conv_direction={conv_direction}")
    print(f"# batch_size={batch_size}")
    print(f"# input_channels={input_channels}")
    print(f"# input_height={input_height}")
    print(f"# input_width={input_width}")
    print(f"# output_channels={output_channels}")
    print(f"# kernel_height={kernel_height}")
    print(f"# kernel_width={kernel_width}")
    print(f"# stride_h={stride_h}")
    print(f"# stride_w={stride_w}")
    print(f"# group_count={group_count}")
    print(f"# search_strategy={search_strategy}")
    print(f"# warmup_iters={warmup_iters}")
    print(f"# num_iterations={num_iterations}")

    command = [
        args.harness,
        "--dtype",
        dtype,
        "--input-source",
        input_source,
        "--conv-direction",
        conv_direction,
        "--batch-size",
        batch_size,
        "--input-channels",
        input_channels,
        "--input-height",
        input_height,
        "--input-width",
        input_width,
        "--output-channels",
        output_channels,
        "--kernel-height",
        kernel_height,
        "--kernel-width",
        kernel_width,
        "--stride-h",
        stride_h,
        "--stride-w",
        stride_w,
        "--group-count",
        group_count,
        "--search-strategy",
        search_strategy,
        "--warmup-iters",
        warmup_iters,
        "--num-iterations",
        num_iterations,
    ]
    timeout_sec = estimate_timeout(
        int(float(num_iterations)),
        int(float(warmup_iters)),
        int(float(input_height)),
        len(directions),
    )
    params = {
        "dtype": dtype,
        "input_source": input_source,
        "conv_direction": conv_direction,
        "batch_size": batch_size,
        "input_channels": input_channels,
        "input_height": input_height,
        "input_width": input_width,
        "output_channels": output_channels,
        "kernel_height": kernel_height,
        "kernel_width": kernel_width,
        "stride_h": stride_h,
        "stride_w": stride_w,
        "group_count": group_count,
        "search_strategy": search_strategy,
        "warmup_iters": warmup_iters,
        "num_iterations": num_iterations,
    }
    rows: list[dict[str, object]] = []
    for pass_index in (1,):  # one timed pass
        print(f"# timed_pass={pass_index}")
        code, text = run_text(command, timeout=timeout_sec)
        print(f"# check=cudnn-conv-pass{pass_index} exit={code}")
        print(text.rstrip())
        print()
        if code != 0:
            raise SystemExit(f"[FAIL] cudnn_conv harness exited {code} on pass {pass_index}")
        rows.append(pass_row(text, conv_direction, params, f"pass{pass_index}"))

    if len(rows) < 1:
        raise SystemExit("[FAIL] Collector must emit at least one timed sample.")

    rows.append(summarize_passes(rows, params))

    fieldnames = ["check", "status", *PARAM_FIELDS, *METRIC_FIELDS]
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
