#!/usr/bin/env python3
"""STREAM collector for workloads 107, 207, 307 and 407.

Compiles src/stream.c and runs it STREAM_SAMPLES times (one). Each run is one
sample; num_iterations is split across the runs (all of it goes to the one run). Full STREAM output goes to the raw file (and
run.log); stdout gets one progress line per run and one line per sample.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

# One STREAM run, one sample. STREAM already keeps the best of NTIMES iterations.
STREAM_SAMPLES = 1
HEADER = [
    "sample_index", "status", "copy_bandwidth_gb_s", "scale_bandwidth_gb_s",
    "add_bandwidth_gb_s", "triad_bandwidth_gb_s", "working_set_bytes", "error_message",
]


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def load_params(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return cfg.get("sweep") or {}


def csv_text(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    return buf.getvalue()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-format", default="csv")
    # run_benchmark.sh passes these only when --help lists them. Without them a
    # command-line override (e.g. --num-threads 8) was shown as resolved but ignored.
    parser.add_argument("--numa-node", default=None)
    parser.add_argument("--num-threads", default=None)
    parser.add_argument("--thread-affinity", default=None)
    parser.add_argument("--array-size", default=None)
    parser.add_argument("--num-iterations", default=None)
    return parser.parse_args()


def numactl_or_plain(command: list[str]) -> tuple[list[str], str]:
    """Keep a leading numactl only when the host accepts that exact bind.

    Containers often ship numactl with no NUMA policy ("This system does not
    support NUMA policy") or without permission to set one. The bind is probed
    on /bin/true with the same flags; on failure the benchmark runs unbound and
    the reason is returned so it can be logged.
    """
    if not command or command[0] != "numactl":
        return list(command), ""
    index = 1
    while index < len(command) and command[index].startswith("-"):
        index += 1
    flags = command[1:index]
    try:
        probe = subprocess.run(["numactl", *flags, "true"], capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return command[index:], f"numactl bind skipped: {exc}"
    if probe.returncode == 0:
        return list(command), ""
    lines = ((probe.stderr or "") + (probe.stdout or "")).strip().splitlines()
    return command[index:], "numactl bind skipped: " + (lines[0] if lines else f"rc={probe.returncode}")


def ntimes_per_sample(total: int, samples: int) -> int:
    # STREAM discards its first pass, so each run needs NTIMES >= 2.
    return max(2, math.ceil(total / samples))


def parse_rates(text: str) -> tuple[dict[str, float], str]:
    """GB/s per kernel, and the first kernel STREAM did not report ("" if none)."""
    rates = {}
    for name in ("copy", "scale", "add", "triad"):
        match = re.search(rf"^{name.capitalize()}:\s+([0-9]+(?:\.[0-9]+)?)", text, re.I | re.M)
        if not match:
            return rates, name
        rates[name] = round(float(match.group(1)) / 1000.0, 4)  # MB/s -> GB/s
    return rates, ""


def main() -> int:
    args = parse_args()
    params = load_params(args.config)

    def value(cli, key, default):
        return str(cli if cli not in (None, "") else pv(params, key, args.profile, default))

    threads = value(args.num_threads, "num_threads", "4")
    array_size = value(args.array_size, "array_size", "10000000")
    total_ntimes = int(float(value(args.num_iterations, "num_iterations", "10")))
    numa_node = value(args.numa_node, "numa_node", "0").strip()
    affinity = value(args.thread_affinity, "thread_affinity", "").strip()
    ntimes = ntimes_per_sample(total_ntimes, STREAM_SAMPLES)

    binary = Path("build/stream")
    binary.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gcc", "-O3", "-fopenmp", f"-DSTREAM_ARRAY_SIZE={array_size}", f"-DNTIMES={ntimes}",
         "src/stream.c", "-o", str(binary)],
        check=True,
    )
    Path("bin").mkdir(exist_ok=True)
    if binary.is_file():
        shutil.copy2(binary, Path("bin/stream"))

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = threads
    if affinity.lower() == "core":
        env["OMP_PROC_BIND"] = "close"
    command = [str(binary)]
    if shutil.which("numactl") and numa_node not in {"", "none"}:
        command = ["numactl", f"--cpunodebind={numa_node}", f"--membind={numa_node}", *command]
    if affinity and affinity.lower() not in {"", "none", "core"} and shutil.which("numactl"):
        bind = affinity.split(":", 1)[1] if affinity.lower().startswith("node:") else affinity
        flag = "--cpunodebind" if affinity.lower().startswith("node:") else "--physcpubind"
        if command[0] == "numactl":
            command.insert(1, f"{flag}={bind}")
        else:
            command = ["numactl", f"{flag}={bind}", *command]
    command, numa_note = numactl_or_plain(command)
    if numa_note:
        print(f"[WARN] {numa_note}", file=sys.stderr)

    # 0.05 s per iteration was sized for a 10M-element array. Time per iteration
    # grows with the array, so scale the allowance (407 extended, 40M x 32000,
    # was killed at the old 1660 s limit).
    per_iter = 0.05 * max(1.0, float(array_size or 10000000) / 10000000.0)
    timeout = max(120, int(ntimes * per_iter) + 120)

    raw_parts: list[str] = []
    rows = []
    rc = 0
    for sample in range(STREAM_SAMPLES):
        print(f"[INFO] STREAM run {sample + 1}/{STREAM_SAMPLES}: {threads} threads, "
              f"{array_size} elements, NTIMES={ntimes}", flush=True)
        completed = subprocess.run(command, check=False, capture_output=True, text=True, env=env, timeout=timeout)
        text = (completed.stdout or "") + "\n" + (completed.stderr or "")
        raw_parts.append(f"===== STREAM run {sample + 1}/{STREAM_SAMPLES} =====\n{text}")
        rates, name = parse_rates(text)
        if name:
            print(text, file=sys.stderr)
            print(f"[FAIL] STREAM did not report {name} (run {sample + 1}/{STREAM_SAMPLES})", file=sys.stderr)
            return 1
        rc = rc or completed.returncode
        rows.append({
            "status": "ok", "copy_bandwidth_gb_s": rates["copy"], "scale_bandwidth_gb_s": rates["scale"],
            "add_bandwidth_gb_s": rates["add"], "triad_bandwidth_gb_s": rates["triad"],
            "working_set_bytes": int(float(array_size)) * 8 * 3, "error_message": "",
        })
        print(f"[INFO] sample {sample}: Copy {rates['copy']:.2f} | Scale {rates['scale']:.2f} | "
              f"Add {rates['add']:.2f} | Triad {rates['triad']:.2f} GB/s", flush=True)

    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    Path(args.raw_file).parent.mkdir(parents=True, exist_ok=True)
    Path(args.raw_file).write_text("\n".join(raw_parts) + "\n" + csv_text(rows), encoding="utf-8")
    print(f"[PASS] collected {len(rows)} samples; full STREAM output: {args.raw_file}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
