#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Run bin/ecc_walk on GPU memory. Fail if CUDA walk did not run.
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import time
from pathlib import Path

import yaml

ECC_DISABLED = "na (expected: ECC disabled)"
ECC_NOT_REPORTED = "na (expected: nvidia-smi reports no ECC counters)"
ECC_KEYS = (
    "uncorrected_ecc_errors_count",
    "corrected_ecc_errors_count",
    "uncorrected_ecc_aggregate_count",
    "corrected_ecc_aggregate_count",
    "uncorrected_ecc_nonzero_field_count",
    "corrected_ecc_nonzero_field_count",
)


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def duration_seconds(raw, default=5.0) -> float:
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return default
    return number / 1000.0 if number >= 10000 else number


def sum_ecc_counters(text: str) -> dict[str, float]:
    """Sum Uncorrectable/Correctable integers. Volatile and aggregate stay separate.

    The published error counts are the volatile sums. The old line-count of
    nonzero fields is kept under *_nonzero_field_count.
    """
    section = ""
    volatile = {"uncorrected": 0, "corrected": 0}
    aggregate = {"uncorrected": 0, "corrected": 0}
    nonzero = {"uncorrected": 0, "corrected": 0}
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped == "volatile" or stripped.startswith("volatile "):
            section = "volatile"
            continue
        if stripped == "aggregate" or stripped.startswith("aggregate "):
            section = "aggregate"
            continue
        match = re.search(r"(Uncorrectable|Correctable)\s*:\s*(\d+)", line, re.I)
        if not match:
            continue
        kind = "uncorrected" if match.group(1).lower().startswith("uncorrect") else "corrected"
        value = int(match.group(2))
        if value:
            nonzero[kind] += 1
        if section == "aggregate":
            aggregate[kind] += value
        else:
            volatile[kind] += value
    return {
        "uncorrected_ecc_errors_count": float(volatile["uncorrected"]),
        "corrected_ecc_errors_count": float(volatile["corrected"]),
        "uncorrected_ecc_aggregate_count": float(aggregate["uncorrected"]),
        "corrected_ecc_aggregate_count": float(aggregate["corrected"]),
        "uncorrected_ecc_nonzero_field_count": float(nonzero["uncorrected"]),
        "corrected_ecc_nonzero_field_count": float(nonzero["corrected"]),
    }


def ecc_unavailable_reason(text: str) -> str:
    """Return an expected-na reason when nvidia-smi has no ECC counts to read, else "".

    With ECC disabled every counter prints as N/A, so the integer sum above was 0 and
    204/404 published "0 errors" for a check that measured nothing.
    """
    counted = re.search(r"(Uncorrectable|Correctable)\s*:\s*\d+", text, re.I)
    if counted:
        return ""
    if re.search(r"^\s*Current\s*:\s*Disabled\b", text, re.I | re.M):
        return ECC_DISABLED
    return ECC_NOT_REPORTED


def read_ecc_text() -> str:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "-q", "-d", "ECC"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (completed.stdout or "") + (completed.stderr or "")


def read_ecc_counters() -> dict[str, float]:
    return sum_ecc_counters(read_ecc_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}
    seconds = max(1.0, duration_seconds(pv(sweep, "duration", args.profile, 5), 5))
    iters = max(1, int(float(pv(sweep, "num_iterations", args.profile, 2) or 2)))
    mem_gb = max(0.125, float(pv(sweep, "memory_size", args.profile, 0.25) or 0.25))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if not Path("bin/ecc_walk").is_file():
        subprocess.run(["bash", "scripts/build.sh"], check=True)
    if not Path("bin/ecc_walk").is_file():
        raise SystemExit("[FAIL] bin/ecc_walk missing; CUDA SDC walk was not built")
    n = max(1024, int(mem_gb * (1024 ** 3) / 4))
    ecc_before_text = read_ecc_text()
    (run_dir / "ecc_before.txt").write_text(ecc_before_text, encoding="utf-8")
    ecc_before = sum_ecc_counters(ecc_before_text)
    start = time.time()
    completed = subprocess.run(
        ["bin/ecc_walk", str(n), str(seconds), str(iters)],
        check=False, capture_output=True, text=True, timeout=int(seconds) + 120,
    )
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    (run_dir / "ecc_walk.txt").write_text(text, encoding="utf-8")
    wall = time.time() - start
    match = re.search(
        r"loops=(\d+)\s+failed_loops=(\d+)\s+failures=(\d+)\s+bytes=(\d+)",
        text,
    )
    if not match:
        detail = " | ".join(line.strip() for line in text.splitlines() if line.strip())[-400:]
        raise SystemExit(
            f"[FAIL] CUDA ecc_walk exited {completed.returncode} without a loops= line "
            f"(a CUDA error stops the walk before it reports): {detail or 'no output'}"
        )
    loops = int(match.group(1))
    failed_loops = int(match.group(2))
    failures = int(match.group(3))
    bytes_walked = int(match.group(4))
    coverage_gb = bytes_walked / (1024 ** 3)
    ecc_after_text = read_ecc_text()
    (run_dir / "ecc_after.txt").write_text(ecc_after_text, encoding="utf-8")
    ecc_after = sum_ecc_counters(ecc_after_text)
    ecc_counts: dict[str, object] = dict(ecc_after)
    for key in ("uncorrected_ecc_errors_count", "corrected_ecc_errors_count"):
        ecc_counts[key] = float(max(0.0, ecc_after[key] - ecc_before[key]))
    unavailable = ecc_unavailable_reason(ecc_before_text) or ecc_unavailable_reason(ecc_after_text)
    if unavailable:
        print(f"[INFO] ECC counters not measured: {unavailable}", flush=True)
        for key in ECC_KEYS:
            ecc_counts[key] = unavailable
    pass_rate = 100.0 * (loops - failed_loops) / loops if loops else 0.0
    row = {
        "status": "ok" if completed.returncode == 0 and failures == 0 and loops > 0 else "error",
        **ecc_counts,
        "device_buffer_gib": coverage_gb,
        "fixed_pattern_fill_verify_pass_rate": pass_rate,
        "test_wall_clock_completion_time_s": wall,
        "error_message": "" if failures == 0 else f"{failures} mismatches in {failed_loops} of {loops} loops",
    }
    header = [
        "sample_index", "status", "uncorrected_ecc_errors_count", "corrected_ecc_errors_count",
        "uncorrected_ecc_aggregate_count", "corrected_ecc_aggregate_count",
        "uncorrected_ecc_nonzero_field_count", "corrected_ecc_nonzero_field_count",
        "device_buffer_gib", "fixed_pattern_fill_verify_pass_rate",
        "test_wall_clock_completion_time_s", "error_message",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    writer.writerow({"sample_index": 0, **row})
    writer.writerow({"sample_index": 1, **row})
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")
    return 0 if row["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
