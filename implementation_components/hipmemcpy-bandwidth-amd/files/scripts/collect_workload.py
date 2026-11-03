#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import os
import subprocess
import sys
from pathlib import Path

import yaml


BANDWIDTH_SIZE_FLOOR = 256 * 1024**2
BANDWIDTH_ITERATION_FLOOR = 10


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
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    if not Path("bin/hip_memcpy_bw").is_file():
        subprocess.run(["bash", "scripts/build.sh"], check=False)
    extras = []
    for key, flag in (
        ("direction", "--direction"), ("pinned_memory", "--pinned-memory"),
        ("min_bytes", "--min-bytes"), ("max_bytes", "--max-bytes"),
        ("step_factor", "--step-factor"), ("warmup_iters", "--warmup-iters"),
        ("num_iterations", "--num-iterations"), ("num_iterations", "-n"),
        ("max_bytes", "-b"),
    ):
        value = pv(params, key, args.profile, "")
        if key == "max_bytes":
            value = max(BANDWIDTH_SIZE_FLOOR, int(float(value or 0)))
        elif key == "num_iterations":
            value = max(BANDWIDTH_ITERATION_FLOOR, int(float(value or 0)))
        if value:
            extras.extend([flag, str(value)])
    timeout = 3600
    try:
        device_id = str(pv(params, "device_id", args.profile, "0") or "0")
        env = os.environ.copy()
        env["HIP_VISIBLE_DEVICES"] = device_id
        completed = subprocess.run(["bin/hip_memcpy_bw", *extras], check=False, capture_output=True, text=True, timeout=timeout, env=env)
        text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        text = str(exc) + f"\nTimeoutExpired after {timeout}s\n"
    rows = []
    for line in text.splitlines():
        if line.lower().startswith("sample_index") or "," not in line:
            continue
        cells = [part.strip() for part in line.split(",")]
        if len(cells) >= 7 and cells[1] in {"ok", "error"}:
            rows.append({
                "status": cells[1], "direction": cells[2], "pinned_memory": cells[3],
                "transfer_size_bytes": cells[4], "latency_us": cells[5],
                "bandwidth_GBps": cells[6], "error_message": cells[7] if len(cells) > 7 else "",
            })
    if not rows:
        Path(args.raw_file).write_text(text, encoding="utf-8")
        print(text, end="")
        print("[FAIL] hip_memcpy_bw produced no measured rows. direction=all must run H2D+D2H+D2D.", file=sys.stderr)
        return 1
    csv_text = write_csv(args.raw_file, [
        "sample_index", "status", "direction", "pinned_memory", "transfer_size_bytes",
        "latency_us", "bandwidth_GBps", "error_message",
    ], rows)
    Path(args.raw_file).write_text(text + "\n" + csv_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
