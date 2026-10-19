#!/usr/bin/env python3
"""Collect ResNet-50 BF16 inference RESULT samples."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

import yaml

METRIC_FIELDS = [
    "images_per_sec",
    "per_image_latency_msec",
    "batch_latency_max_msec",
    "batch_p99_latency_msec",
    "gpu_utilization_percent",
    "peak_gpu_memory_gb",
]
PARAM_FIELDS = ["check", "batch_size", "headline_batch_size", "dtype", "status"]
RESULT_RE = re.compile(
    r"RESULT dtype=(?P<dtype>\S+) precision=(?P<precision>\S+) image_size=(?P<image_size>\S+) "
    r"batch_size=(?P<batch_size>\S+) images_per_sec=(?P<images_per_sec>[0-9.eE+-]+) "
    r"per_image_latency_msec=(?P<per_image_latency_msec>[0-9.eE+-]+) "
    r"batch_latency_max_msec=(?P<batch_latency_max_msec>[0-9.eE+-]+) "
    r"latency_sample_count=(?P<latency_sample_count>[0-9]+) "
    r"batch_p99_latency_msec=(?P<batch_p99_latency_msec>[0-9.eE+-]+|na) "
    r"gpu_utilization_percent=(?P<gpu_utilization_percent>[0-9.eE+-]+|na) "
    r"peak_gpu_memory_gb=(?P<peak_gpu_memory_gb>[0-9.eE+-]+) status=(?P<status>\w+)"
)

# Printed when no utilization reading was taken during the timed loop.
UTIL_NA_RE = re.compile(r"^UTIL_NA batch_size=(\S+) reason=(na \(.*\))\s*$", re.MULTILINE)
PERCENTILE_NA_RE = re.compile(r"^PERCENTILE_NA batch_size=(\S+) reason=(na \(.*\))\s*$", re.MULTILINE)


def fmt(value: str) -> str:
    """6-decimal number, or an "na (...)" reason unchanged."""
    return value if str(value).startswith("na (") else f"{float(value):.6f}"


def pick(sweep: dict, key: str, profile: str, default: str = "") -> str:
    value = sweep.get(key, default)
    if isinstance(value, dict):
        value = value.get(profile, value.get("smoke", default))
    return "" if value is None else str(value).strip()


def run(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--device-id", default="")
    parser.add_argument("--num-gpus", default="")
    parser.add_argument("--parallel-strategy", default="")
    parser.add_argument("--weights", default="")
    parser.add_argument("--dtype", default="")
    parser.add_argument("--precision", default="")
    parser.add_argument("--image-source", default="")
    parser.add_argument("--image-size", default="")
    parser.add_argument("--use-channels-last", default="")
    parser.add_argument("--batch-size", default="")
    parser.add_argument("--num-workers", default="")
    parser.add_argument("--warmup-iters", default="")
    parser.add_argument("--num-iterations", default="")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep", {})
    profile = args.profile
    repo = Path(__file__).resolve().parents[1]
    python = repo / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path("python3")
    command = [
        str(python),
        str(repo / "scripts" / "gpu-bench-resnet50-pytorch-inference.py"),
        "--device-id",
        args.device_id or pick(sweep, "device_id", profile, "0"),
        "--weights",
        args.weights or pick(sweep, "weights", profile, "random"),
        "--dtype",
        args.dtype or pick(sweep, "dtype", profile, "bf16"),
        "--precision",
        args.precision or pick(sweep, "precision", profile, "bf16"),
        "--image-source",
        args.image_source or pick(sweep, "image_source", profile, "synthetic"),
        "--image-size",
        args.image_size or pick(sweep, "image_size", profile, "64"),
        "--use-channels-last",
        args.use_channels_last or pick(sweep, "use_channels_last", profile, "true"),
        "--batch-size",
        args.batch_size or pick(sweep, "batch_size", profile, "1,2"),
        "--num-workers",
        args.num_workers or pick(sweep, "num_workers", profile, "0"),
        "--warmup-iters",
        args.warmup_iters or pick(sweep, "warmup_iters", profile, "1"),
        "--num-iterations",
        args.num_iterations or pick(sweep, "num_iterations", profile, "3"),
    ]
    print("[RUN] " + " ".join(command))
    code, text = run(command)
    print(text.rstrip())
    if code != 0:
        raise SystemExit("[FAIL] inference script failed.")
    parsed = [m.groupdict() for m in RESULT_RE.finditer(text)]
    na_reasons = {m.group(1): m.group(2) for m in UTIL_NA_RE.finditer(text)}
    p99_reasons = {m.group(1): m.group(2) for m in PERCENTILE_NA_RE.finditer(text)}
    for item in parsed:
        if item["gpu_utilization_percent"] == "na":
            reason = na_reasons.get(item["batch_size"], "na (no utilization reading)")
            if profile == "smoke" and "too short" in reason:
                reason = "na (expected: timed loop shorter than 1s on smoke)"
            item["gpu_utilization_percent"] = reason
        if item["batch_p99_latency_msec"] == "na":
            item["batch_p99_latency_msec"] = p99_reasons.get(
                item["batch_size"],
                "na (p99 requires at least 100 samples)",
            )
    if len(parsed) < 2:
        raise SystemExit("[FAIL] expected at least two RESULT rows from the batch sweep.")
    rows = []
    for item in parsed:
        row = {
            "check": f"batch{item['batch_size']}",
            "batch_size": item["batch_size"],
            "dtype": item["dtype"],
            "status": item["status"],
        }
        for name in METRIC_FIELDS:
            row[name] = fmt(item[name])
        rows.append(row)
    headline = max(rows, key=lambda row: int(float(row["batch_size"])))
    case_fields = [f"case_{name}" for name in METRIC_FIELDS]
    for row in rows:
        row["headline_batch_size"] = headline["batch_size"]
        for name in METRIC_FIELDS:
            row[f"case_{name}"] = row[name]
            row[name] = headline[name]
    summary = {
        "check": "summary",
        "batch_size": headline["batch_size"],
        "headline_batch_size": headline["batch_size"],
        "dtype": parsed[0]["dtype"],
        "status": "ok",
    }
    for name in METRIC_FIELDS:
        summary[name] = headline[name]
        summary[f"case_{name}"] = headline[name]
    rows.append(summary)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    fields = [*PARAM_FIELDS, *METRIC_FIELDS, *case_fields]
    with (run_dir / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (run_dir / "raw_results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (run_dir / "raw_output.txt").write_text(f"===== infer rc={code} =====\n{text}", encoding="utf-8")
    print("# METRICS_CSV")
    print((run_dir / "raw_results.csv").read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
