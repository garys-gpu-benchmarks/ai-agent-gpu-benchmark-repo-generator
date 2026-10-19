#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import time
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

def ras_counter_totals(text: str):
    """(uncorrected, corrected) from key:value text or a RAS table.

    Key:value lines win. Otherwise each data row's last two integers are
    correctable, then uncorrectable. A table that names both columns and
    yields no data row is "na (RAS table not parsed)", not blank and not 0.
    Text that never names the columns stays blank.
    """
    bad = [int(item) for item in re.findall(r"TOTAL_UNCORRECTABLE_COUNT\s*[:=]\s*(\d+)", text, re.I)]
    good = [int(item) for item in re.findall(r"TOTAL_CORRECTABLE_COUNT\s*[:=]\s*(\d+)", text, re.I)]
    if not bad and not good:
        bad = [
            int(item) for item in re.findall(
                r"\bUncorrectable(?:\s+Error)?(?:\s+Count)?\s*[:=|]\s*(\d+)",
                text,
                re.I,
            )
        ]
        good = [
            int(item) for item in re.findall(
                r"\bCorrectable(?:\s+Error)?(?:\s+Count)?\s*[:=|]\s*(\d+)",
                text,
                re.I,
            )
        ]
    if bad or good:
        return float(sum(bad)), float(sum(good))
    low = text.lower()
    names_columns = "uncorrectable" in low and "correctable" in low
    uncorrected = corrected = 0
    rows = 0
    for line in text.splitlines():
        if re.search(r"correctable|uncorrectable", line, re.I):
            continue
        if not re.search(r"[A-Za-z]", line):
            continue
        ints = re.findall(r"\d+", line)
        if len(ints) < 2:
            continue
        corrected += int(ints[-2])
        uncorrected += int(ints[-1])
        rows += 1
    if rows:
        return float(uncorrected), float(corrected)
    if names_columns:
        return "na (RAS table not parsed)", "na (RAS table not parsed)"
    return "", ""


def ecc_counts() -> tuple[str, str]:
    """Read cumulative RAS counters without treating parse failure as zero."""
    for cmd in (
        ["amd-smi", "metric"],
        ["/opt/rocm/bin/amd-smi", "metric"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (out.stdout or "") + "\n" + (out.stderr or "")
        uncorrected, corrected = ras_counter_totals(text)
        if uncorrected != "" or corrected != "":
            return uncorrected, corrected
    return "", ""


def counter_delta(before, after):
    for item in (before, after):
        if isinstance(item, str) and item.strip().lower().startswith("na ("):
            return item
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return ""
    return float(max(0.0, after - before))


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    seconds = max(1.0, duration_seconds(pv(params, "duration", args.profile, 5)))
    iters = max(1, int(float(pv(params, "num_iterations", args.profile, 2) or 2)))
    mem_gb = max(0.125, float(pv(params, "memory_size", args.profile, 1) or 1))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    import torch
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    requested = int(mem_gb * (1024 ** 3))
    if device.type == "cuda":
        free, _total = torch.cuda.mem_get_info(device)
        # Honor the profile's memory_size (it used to be raised to 5% of the GPU,
        # so "--memory-size 1" allocated about 10 GB on an MI300X). Cap at half
        # the free memory.
        target = min(requested, int(free * 0.50))
    else:
        target = requested
    n = max(1024, target // 4)
    coverage_gb = (n * 4 / 1e9) if device.type == "cuda" else ""
    ecc_before = ecc_counts()
    start = time.time()
    failed_checks = 0
    loops = 0
    while time.time() - start < seconds:
        for _ in range(iters):
            buf = torch.zeros(n, device=device, dtype=torch.int32)
            buf[::2] = 1
            mismatch_count = int((buf[::2] != 1).sum().item())
            mismatch_count += int((buf[1::2] != 0).sum().item())
            if mismatch_count:
                failed_checks += 1
            loops += 1
            if time.time() - start >= seconds:
                break
    wall = time.time() - start
    ecc_after = ecc_counts()
    uncorrected = counter_delta(ecc_before[0], ecc_after[0])
    corrected = counter_delta(ecc_before[1], ecc_after[1])
    pass_rate = 100.0 * (loops - failed_checks) / loops if loops else 0.0
    write_csv(args.raw_file, [
        "sample_index", "status", "uncorrected_ecc_errors_count", "corrected_ecc_errors_count",
        "allocated_verification_buffer_gb", "loop_verification_pass_pct",
        "test_wall_clock_completion_time_s", "error_message",
    ], [{
        "status": "ok" if failed_checks == 0 else "error",
        "uncorrected_ecc_errors_count": uncorrected,
        "corrected_ecc_errors_count": corrected,
        "allocated_verification_buffer_gb": coverage_gb,
        "loop_verification_pass_pct": pass_rate,
        "test_wall_clock_completion_time_s": wall,
        "error_message": "" if failed_checks == 0 else f"{failed_checks} failed checks in {loops} loops",
    }])
    return 0 if failed_checks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
