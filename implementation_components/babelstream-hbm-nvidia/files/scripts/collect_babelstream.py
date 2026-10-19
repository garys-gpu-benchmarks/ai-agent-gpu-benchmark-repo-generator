#!/usr/bin/env python3
"""Collect BabelStream-style CUDA HBM bandwidth samples."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

import yaml

# The binary prints copy_bandwidth_gb_s. The workbook key is bandwidth_gb_s_copy.
PRINT_TO_METRIC = {
    "copy_bandwidth_gb_s": "bandwidth_gb_s_copy",
    "mul_bandwidth_gb_s": "bandwidth_gb_s_mul",
    "add_bandwidth_gb_s": "bandwidth_gb_s_add",
    "triad_bandwidth_gb_s": "bandwidth_gb_s_triad",
    "dot_bandwidth_gb_s": "bandwidth_gb_s_dot",
}
METRIC_FIELDS = list(PRINT_TO_METRIC.values())
PARAM_FIELDS = ["check", "device_id", "array_size", "dtype", "block_size", "status"]
KV_RE = re.compile(r"^([A-Za-z0-9_]+)=([0-9]+(?:\.[0-9]+)?)\s*$", re.MULTILINE)


def pick(sweep: dict, key: str, profile: str, default: str = "") -> str:
    value = sweep.get(key, default)
    if isinstance(value, dict):
        value = value.get(profile, value.get("smoke", default))
    return "" if value is None else str(value).strip()


def parse_kv(text: str) -> dict[str, float]:
    return {m.group(1): float(m.group(2)) for m in KV_RE.finditer(text)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", default="")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--device-id", default="")
    parser.add_argument("--dtype", default="")
    parser.add_argument("--block-size", default="")
    parser.add_argument("--array-size", default="")
    parser.add_argument("--kernels", default="")
    parser.add_argument("--warmup-iters", default="")
    parser.add_argument("--num-iterations", default="")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep", {})
    profile = args.profile
    device = args.device_id or pick(sweep, "device_id", profile, "0")
    dtype = args.dtype or pick(sweep, "dtype", profile, "FP64")
    block = args.block_size or pick(sweep, "block_size", profile, "256")
    array_size = args.array_size or pick(sweep, "array_size", profile, "1048576")
    warmup = args.warmup_iters or pick(sweep, "warmup_iters", profile, "1")
    iters = args.num_iterations or pick(sweep, "num_iterations", profile, "2")
    repo = Path(__file__).resolve().parents[1]
    binary = repo / "bin" / "babelstream"
    if not binary.is_file():
        build = subprocess.run(["bash", str(repo / "scripts" / "build.sh")], cwd=repo, check=False, text=True, capture_output=True)
        print(build.stdout)
        if build.returncode != 0 or not binary.is_file():
            raise SystemExit("[FAIL] babelstream compile failed.")
    command = [
        str(binary), "--device", str(device), "--array-size", str(int(float(array_size))),
        "--block-size", str(int(float(block))), "--warmup", str(int(float(warmup))),
        "--iters", str(int(float(iters))),
    ]
    print("[RUN] " + " ".join(command))
    completed = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f"# babelstream_exit={completed.returncode}")
    print(completed.stdout.rstrip())
    parsed = parse_kv(completed.stdout)
    if completed.returncode != 0 or "triad_bandwidth_gb_s" not in parsed:
        raise SystemExit("[FAIL] babelstream did not report kernel bandwidths.")
    latest = {}
    for printed, metric in PRINT_TO_METRIC.items():
        latest[metric] = parsed.get(printed, parsed.get(metric, 0.0))
    if any(latest[name] <= 0 for name in METRIC_FIELDS):
        raise SystemExit(f"[FAIL] non-positive BabelStream metrics: {latest}")
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for kernel in ("Copy", "Mul", "Add", "Triad", "Dot"):
        row = {"check": kernel, "device_id": device, "array_size": array_size, "dtype": dtype, "block_size": block, "status": "ok"}
        for name in METRIC_FIELDS:
            row[name] = f"{latest[name]:.6f}"
        rows.append(row)
    element = 8 if "64" in str(dtype) else 4 if "32" in str(dtype) else 2
    working_set = int(float(array_size)) * element * 3
    summary = {
        "check": "summary", "device_id": device, "array_size": array_size, "dtype": dtype,
        "block_size": block, "status": "ok", "working_set_bytes": working_set,
    }
    for name in METRIC_FIELDS:
        summary[name] = f"{latest[name]:.6f}"
    rows.append(summary)
    fields = [*PARAM_FIELDS, *METRIC_FIELDS, "working_set_bytes"]
    with (run_dir / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (run_dir / "raw_results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (run_dir / "raw_output.txt").write_text(f"===== babelstream rc={completed.returncode} =====\n{completed.stdout}", encoding="utf-8")
    print("# METRICS_CSV")
    print((run_dir / "raw_results.csv").read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
