#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
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
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    text = buf.getvalue()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
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
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    helper = Path("scripts/collect_numa_cache.py")
    overlay = Path(args.run_dir) / "overlay.csv"
    cmd = [sys.executable, str(helper), "--output", str(overlay), "--config", args.config, "--profile", args.profile]
    completed = subprocess.run(cmd, check=False, text=True)
    if completed.returncode != 0:
        return completed.returncode
    header = [
        "source_numa_node", "target_numa_node", "working_set_size", "cache_level",
        "access_pattern", "stride", "num_threads", "page_size",
        "local_numa_node_latency_nsec", "remote_numa_node_latency_nsec",
        "cross_socket_numa_penalty_ratio", "local_dram_pointer_chase_bandwidth_gb_s",
        "cache_miss_counters_misses_sec", "cache_latency_nsec",
    ]
    rows = []
    if overlay.is_file():
        with overlay.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("check", "")).lower() != "summary":
                    continue
                rows.append({key: row.get(key, "") for key in header})
    if overlay.is_file() and not rows:
        text = overlay.read_text(encoding="utf-8")
        Path(args.raw_file).write_text(text, encoding="utf-8")
        return 0
    write_csv(args.raw_file, header, rows or [{key: "" for key in header}])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
