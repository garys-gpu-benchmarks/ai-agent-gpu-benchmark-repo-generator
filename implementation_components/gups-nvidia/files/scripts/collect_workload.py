#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Run OpenMP bin/gups. Cap iterations. TLB/L3 only from perf.
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def cap_iters(profile: str, requested: int) -> int:
    # Safety cap only. Was 200/500, which silently truncated the workbook's
    # baseline/extended num_iterations and pinned 213/413 at ~1 min / ~5 min.
    limits = {"smoke": 2, "baseline": 5000, "extended": 10000}
    return max(1, min(requested, limits.get(profile, 8)))


def parse_gups(text: str) -> dict[str, float]:
    out = {}
    for key in ("table_size", "updates", "iters", "threads", "seconds", "gups", "updates_sec"):
        match = re.search(rf"{key}=([0-9.eE+-]+)", text)
        if match:
            out[key] = float(match.group(1))
    return out


def strip_numactl(command: list[str]) -> list[str]:
    """Drop a leading numactl and its flags. The gups binary follows those flags."""
    if not command or command[0] != "numactl":
        return list(command)
    index = 1
    while index < len(command) and command[index].startswith("-"):
        index += 1
    return command[index:]


def try_perf(command: list[str], timeout: int) -> dict[str, float]:
    if not shutil.which("perf"):
        return {}
    completed = subprocess.run(
        ["perf", "stat", "-e", "dTLB-load-misses,cache-misses,instructions", "--", *command],
        check=False, capture_output=True, text=True, timeout=timeout,
    )
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    counts = {}
    for name in ("dtlb-load-misses", "cache-misses", "instructions"):
        match = re.search(rf"([0-9]+(?:\.[0-9]+)?)\s+{name}", text.replace(",", ""), re.I)
        if match:
            counts[name] = float(match.group(1))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    params = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}
    table_size = max(1024, int(float(pv(params, "table_size", args.profile, 4194304) or 4194304)))
    updates = max(1, int(float(pv(params, "num_updates", args.profile, 1000000) or 1000000)))
    requested = max(1, int(float(pv(params, "num_iterations", args.profile, 1) or 1)))
    iters = cap_iters(args.profile, requested)
    seed = int(float(pv(params, "seed", args.profile, 42) or 42))
    threads = max(1, int(float(pv(params, "num_threads", args.profile, 1) or 1)))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if not Path("bin/gups").is_file():
        subprocess.run(["bash", "scripts/build.sh"], check=True)
    if not Path("bin/gups").is_file():
        raise SystemExit("[FAIL] bin/gups missing")
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(threads)
    affinity = str(pv(params, "thread_affinity", args.profile, "") or "").strip()
    if affinity.lower() == "core":
        env["OMP_PROC_BIND"] = "close"
    numa_node = str(pv(params, "numa_node", args.profile, "0") or "").strip()
    command = ["bin/gups", str(table_size), str(updates), str(iters), str(seed)]
    if shutil.which("numactl") and numa_node not in {"", "none"}:
        command = ["numactl", f"--cpunodebind={numa_node}", f"--membind={numa_node}", *command]
    if affinity and affinity.lower() not in {"", "none", "core"} and shutil.which("numactl"):
        bind = affinity.split(":", 1)[1] if affinity.lower().startswith("node:") else affinity
        flag = "--cpunodebind" if affinity.lower().startswith("node:") else "--physcpubind"
        if command[0] == "numactl":
            command.insert(1, f"{flag}={bind}")
        else:
            command = ["numactl", f"{flag}={bind}", *command]
    ran = command
    completed = subprocess.run(ran, check=False, capture_output=True, text=True, env=env, timeout=3600)
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    # Containers often have numactl installed and no NUMA policy. The workbook
    # still names node 0; the score is the gups run, so retry without the bind.
    if ran and ran[0] == "numactl" and "does not support NUMA" in text:
        ran = strip_numactl(ran)
        completed = subprocess.run(ran, check=False, capture_output=True, text=True, env=env, timeout=3600)
        text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    (run_dir / "gups.txt").write_text(text, encoding="utf-8")
    parsed = parse_gups(text)
    if completed.returncode != 0 or "gups" not in parsed:
        raise SystemExit(f"[FAIL] gups did not report a score: {text[-400:]}")
    perf_counts = try_perf(ran, 3600)
    instructions = perf_counts.get("instructions", 0.0)
    pmu_na = "na (expected: PMU access denied)"
    tlb_measured = bool(instructions and "dtlb-load-misses" in perf_counts)
    l3_measured = bool(instructions and "cache-misses" in perf_counts)
    tlb = (1000.0 * perf_counts["dtlb-load-misses"] / instructions) if tlb_measured else pmu_na
    l3 = (100.0 * perf_counts["cache-misses"] / instructions) if l3_measured else pmu_na
    row = {
        "status": "ok",
        "giga_updates_score": parsed["gups"],
        "tlb_miss_rate": tlb,
        "l3_cache_miss_rate": l3,
        "random_64_bit_update_rate": parsed.get("updates_sec", 0.0),
        "updates_sec": parsed.get("updates_sec", 0.0),
        "payload_update_gb_s": parsed.get("updates_sec", 0.0) * 8.0 / 1e9,
        "num_threads": threads,
        "num_iterations_ran": iters,
        "num_iterations_requested": requested,
        "microarch_measured": 1 if tlb_measured else 0,
        "error_message": "" if tlb_measured else "perf TLB/L3 not measured",
    }
    header = [
        "sample_index", "status", "giga_updates_score", "tlb_miss_rate", "l3_cache_miss_rate",
        "random_64_bit_update_rate", "updates_sec", "payload_update_gb_s",
        "num_threads", "num_iterations_ran", "num_iterations_requested",
        "microarch_measured", "error_message",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    writer.writerow({"sample_index": 0, **row})
    writer.writerow({"sample_index": 1, **row})
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
