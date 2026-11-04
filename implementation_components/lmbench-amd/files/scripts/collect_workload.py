#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import shutil
import subprocess
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

def lmbench_bin(name):
    for root in ("/usr/lib/lmbench/bin", "/usr/lib/lmbench/bin/x86_64-linux-gnu", "bin"):
        path = Path(root) / name
        if path.is_file():
            return str(path)
    return shutil.which(name) or name



_LMB_NUM = r"([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"


def lmbench_value(tool: str, text: str):
    """Return (value, units) for one lmbench tool's output, or (None, units).

    Each lmbench tool prints its result in a different place; taking the first
    number on the line (the old behavior) returned the *setting*, not the
    result, for lat_ctx ("2 3.06" -> process count 2), bw_mem ("8.39 22473.50"
    -> buffer size in MB) and lat_mem_rd (first array size in MB).
    """
    import re
    pairs = []
    for line in text.splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) >= 2:
            try:
                pairs.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    if tool == "lat_syscall":
        m = re.search(r":\s*" + _LMB_NUM + r"\s*microseconds", text)
        return (float(m.group(1)) if m else None), "us"
    if tool == "lat_ctx":
        return (pairs[-1][1] if pairs else None), "us"
    if tool == "lat_mem_rd":
        # lat_mem_rd prints "<working-set MB> <latency ns>". Select the
        # requested 16 MB point explicitly; output order varies by build.
        point = min(pairs, key=lambda pair: abs(pair[0] - 16.0)) if pairs else None
        return (point[1] if point and abs(point[0] - 16.0) < 0.01 else None), "ns"
    if tool == "bw_mem":
        return (pairs[0][1] if pairs else None), "MB/s"
    if tool == "bw_pipe":
        m = re.search(r"bandwidth:\s*" + _LMB_NUM, text, re.I)
        return (float(m.group(1)) if m else None), "MB/s"
    return None, "raw"


def warmup_args(params, profile) -> list[str]:
    """lmbench -W <warmup>: microseconds each benchmark runs untimed before its
    timed repetitions (lmbench's benchmp warmup). lat_syscall, lat_ctx,
    lat_mem_rd, bw_mem and bw_pipe all take it before their positional
    arguments. lat_mem_rd warms up once per array size, so keep this small.
    Empty or 0 passes nothing (lmbench's default of no warmup)."""
    raw = pv(params, "warmup_duration_us", profile, "")
    try:
        value = int(float(raw)) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        raise SystemExit(f"[FAIL] warmup_duration_us must be a number of microseconds, got {raw!r}")
    return ["-W", str(value)] if value > 0 else []


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    reps = max(1, int(float(pv(params, "repetitions", args.profile, 1) or 1)))
    timeout = {"smoke": 120, "baseline": 180, "extended": 180}.get(args.profile, 180)
    warm = warmup_args(params, args.profile)
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    tests = [
        (["lat_syscall", "null"], "lat_syscall_null_us"),
        (["lat_syscall", "read"], "lat_syscall_read"),
        (["lat_syscall", "write"], "lat_syscall_write"),
        (["lat_ctx", "-s", "0", "2"], "context_switch_latency_us"),
        (["lat_mem_rd", "16", "128"], "lat_mem_rd_16mb_stride128_ns"),
        # 512 MB exceeds typical server LLC capacity; 8 MB measured cache.
        (["bw_mem", "512m", "rd"], "bw_mem_mb_s"),
        (["bw_pipe"], "bw_pipe_mb_s"),
    ]
    rows = []
    for _rep in range(reps):
        for argv, name in tests:
            cmd = [lmbench_bin(argv[0]), *warm, *argv[1:]]
            try:
                completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                text = (completed.stdout or "") + " " + (completed.stderr or "")
                (Path(args.run_dir) / f"{name}.txt").write_text(text, encoding="utf-8")
                value, units = lmbench_value(argv[0], text)
                # No parsable result -> blank ("not measured"), never an invented 1.0.
                rows.append({"benchmark": name, "units": units, "value": "" if value is None else value})
            except subprocess.TimeoutExpired:
                rows.append({"benchmark": name, "units": "timeout", "value": ""})
    write_csv(args.raw_file, ["benchmark", "units", "value"], rows or [{"benchmark": "lmbench", "units": "error", "value": 0.0}])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
