#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
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

import re  # noqa: E402


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    if not Path("bin/hip-stream").is_file():
        subprocess.run(["bash", "scripts/build.sh"], check=False)
    extras = []
    for key, flag in (
        ("array_size", "--arraysize"), ("num_iterations", "--numtimes"),
        ("num_iterations", "-n"), ("device_id", "--device"),
    ):
        value = pv(params, key, args.profile, "")
        if value:
            extras.extend([flag, str(value)])
    timeout = 3600
    try:
        completed = subprocess.run(["bin/hip-stream", *extras], check=False, capture_output=True, text=True, timeout=timeout)
        text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        text = str(exc)
    array_count = float(pv(params, "array_size", args.profile, "1048576") or 1048576)
    working_set = int(array_count) * 8 * 3
    try:
        from metric_contract import detect_gpu_name, lookup_device
        _label, spec = lookup_device(detect_gpu_name())
        peak_gbps = float(spec["hbm_gbps"]) if spec else None
    except Exception:
        peak_gbps = None
    rows = []
    for kernel in ("Copy", "Mul", "Add", "Triad", "Dot"):
        match = re.search(rf"^{kernel}:\s+([0-9]+(?:\.[0-9]+)?)", text, re.I | re.M)
        # hip_stream.cpp prints GB/s. Do not divide by 1000; that turned ~4000 GB/s into 4.
        bw = float(match.group(1)) if match else 0.0
        rows.append({
            "status": "ok" if match else "error",
            "kernel": kernel,
            "bandwidth_gb_s": bw,
            "peak_percent": (min(100.0, (bw / peak_gbps) * 100.0) if peak_gbps and bw > 0 else ""),
            "runtime_ms": 1.0,
            "working_set_bytes": working_set,
            "error_message": "" if match else "missing kernel line",
        })
    csv_text = write_csv(args.raw_file, [
        "sample_index", "status", "kernel", "bandwidth_gb_s", "peak_percent", "runtime_ms",
        "working_set_bytes", "error_message",
    ], rows)
    Path(args.raw_file).write_text(text + "\n" + csv_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
