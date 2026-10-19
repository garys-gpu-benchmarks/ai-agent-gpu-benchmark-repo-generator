#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
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

import re  # noqa: E402


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    threads = str(pv(params, "num_threads", args.profile, "4"))
    array_size = str(pv(params, "array_size", args.profile, "10000000"))
    ntimes = str(pv(params, "num_iterations", args.profile, "10"))
    binary = Path("build/stream")
    binary.parent.mkdir(parents=True, exist_ok=True)
    src = Path("src/stream.c")
    subprocess.run(
        ["gcc", "-O3", "-fopenmp", f"-DSTREAM_ARRAY_SIZE={array_size}", f"-DNTIMES={ntimes}", str(src), "-o", str(binary)],
        check=True,
    )
    Path("bin").mkdir(exist_ok=True)
    if binary.is_file():
        shutil.copy2(binary, Path("bin/stream"))
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = threads
    # 0.05 s per iteration was sized for a 10M-element array. Time per iteration
    # grows with the array, so scale the allowance (407 extended, 40M x 32000,
    # was killed at the old 1660 s limit).
    per_iter = 0.05 * max(1.0, float(array_size or 10000000) / 10000000.0)
    timeout = max(120, int(float(ntimes or 10) * per_iter) + 120)
    completed = subprocess.run([str(binary)], check=False, capture_output=True, text=True, env=env, timeout=timeout)
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    rates = {}
    for name in ("copy", "scale", "add", "triad"):
        match = re.search(rf"^{name.capitalize()}:\s+([0-9]+(?:\.[0-9]+)?)", text, re.I | re.M)
        if not match:
            print(text, file=sys.stderr)
            print(f"[FAIL] STREAM did not report {name}", file=sys.stderr)
            return 1
        rates[name] = float(match.group(1)) / 1000.0
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    csv_block = write_csv(args.raw_file, [
        "sample_index", "status", "copy_bandwidth_gb_s", "scale_bandwidth_gb_s",
        "add_bandwidth_gb_s", "triad_bandwidth_gb_s", "working_set_bytes", "error_message",
    ], [{
        "status": "ok", "copy_bandwidth_gb_s": rates["copy"], "scale_bandwidth_gb_s": rates["scale"],
        "add_bandwidth_gb_s": rates["add"], "triad_bandwidth_gb_s": rates["triad"],
        "working_set_bytes": int(float(array_size)) * 8 * 3,
        "error_message": "",
    }])
    Path(args.raw_file).write_text(text + "\n" + csv_block, encoding="utf-8")
    print(text)
    print(csv_block, end="")
    return 0 if completed.returncode == 0 else completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
