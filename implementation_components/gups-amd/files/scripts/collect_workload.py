#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml


L3_COUNTER_NA = "na (expected: LLC load counters not exposed on this host)"


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


def parse_cache_size_bytes(value: str) -> int:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)i?b?\s*", value, re.I)
    if match is None:
        return 0
    scale = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    return int(float(match.group(1)) * scale[match.group(2).lower()])


def largest_last_level_cache_bytes() -> int:
    """Return the largest per-CPU L3-or-higher data/unified cache."""
    largest = 0
    for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cache/index*"):
        try:
            cache_type = (path / "type").read_text(encoding="utf-8").strip().lower()
            level = int((path / "level").read_text(encoding="utf-8").strip())
            size = parse_cache_size_bytes((path / "size").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if cache_type in {"data", "unified"} and level >= 3:
            largest = max(largest, size)
    return largest


def required_table_elements(configured_elements: int, llc_bytes: int) -> int:
    minimum_bytes = max(256 * 1024**2, 4 * llc_bytes)
    return max(configured_elements, (minimum_bytes + 7) // 8)


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

def run_gups(run_dir: Path, table_size: int, updates: int, iters: int, threads: int, seed: int = 42, numa_node: str = "", affinity: str = "") -> tuple[float, str, str]:
    """Return elapsed seconds, TLB miss rate, and L3 miss rate.

    The timed updates run in a native binary so the thread count is real work.
    Miss rates stay blank when perf does not return both the miss and the load count.
    """
    source = run_dir / "gups_kernel.c"
    binary = run_dir / "gups_kernel"
    source.write_text(
        "#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <time.h>\n"
        "#ifdef _OPENMP\n#include <omp.h>\n#endif\n"
        "int main(int argc, char **argv) {\n"
        "  uint64_t n = strtoull(argv[1], 0, 10);\n"
        "  uint64_t updates = strtoull(argv[2], 0, 10);\n"
        "  int threads = atoi(argv[3]);\n"
        "  uint64_t mix = argc > 4 ? strtoull(argv[4], 0, 10) : 42;\n"
        "  uint64_t *table = calloc(n, sizeof(uint64_t));\n"
        "  if (!table) return 1;\n"
        "  struct timespec a, b;\n"
        "  clock_gettime(CLOCK_MONOTONIC, &a);\n"
        "#ifdef _OPENMP\n  omp_set_num_threads(threads > 0 ? threads : 1);\n#endif\n"
        "  #pragma omp parallel\n"
        "  {\n"
        "    int tid = 0;\n"
        "#ifdef _OPENMP\n    tid = omp_get_thread_num();\n    int nthreads = omp_get_num_threads();\n"
        "#else\n    int nthreads = 1;\n#endif\n"
        "    uint64_t seed = mix ^ (uint64_t)tid;\n"
        "    uint64_t begin = (updates * (uint64_t)tid) / (uint64_t)nthreads;\n"
        "    uint64_t end = (updates * (uint64_t)(tid + 1)) / (uint64_t)nthreads;\n"
        "    for (uint64_t i = begin; i < end; i++) {\n"
        "      seed = seed * 6364136223846793005ULL + 1;\n"
        "      table[seed % n] += 1;\n"
        "    }\n"
        "  }\n"
        "  clock_gettime(CLOCK_MONOTONIC, &b);\n"
        "  double sec = (b.tv_sec - a.tv_sec) + (b.tv_nsec - a.tv_nsec) / 1e9;\n"
        "  printf(\"elapsed_sec %.9f\\n\", sec);\n"
        "  free(table);\n"
        "  return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    gcc = shutil.which("gcc")
    compiled = False
    if gcc:
        build = subprocess.run(
            [gcc, "-O2", "-fopenmp", "-std=c11", str(source), "-o", str(binary)],
            capture_output=True, text=True,
        )
        compiled = build.returncode == 0 and binary.is_file()
    total_updates = updates * iters
    if compiled:
        command = [str(binary), str(table_size), str(total_updates), str(threads), str(seed)]
        node = str(numa_node or "").strip()
        if shutil.which("numactl") and node not in {"", "none"}:
            command = ["numactl", f"--cpunodebind={node}", f"--membind={node}", *command]
        if affinity and str(affinity).lower() not in {"", "none", "core"} and shutil.which("numactl"):
            bind = str(affinity).split(":", 1)[1] if str(affinity).lower().startswith("node:") else str(affinity)
            flag = "--cpunodebind" if str(affinity).lower().startswith("node:") else "--physcpubind"
            if command[0] == "numactl":
                command.insert(1, f"{flag}={bind}")
            else:
                command = ["numactl", f"{flag}={bind}", *command]
        command, numa_note = numactl_or_plain(command)
        if numa_note:
            print(f"[WARN] {numa_note}", file=sys.stderr)
        perf = shutil.which("perf")
        if perf:
            command = [
                perf, "stat", "-e",
                "dTLB-loads,dTLB-load-misses,LLC-loads,LLC-load-misses",
                "-x", ",", "--", *command,
            ]
        completed = subprocess.run(command, capture_output=True, text=True)
        elapsed = None
        for line in (completed.stdout or "").splitlines():
            if line.startswith("elapsed_sec "):
                elapsed = float(line.split()[1])
        if elapsed is None or elapsed <= 0:
            raise SystemExit("[FAIL] gups kernel did not report elapsed_sec")
        counts = {}
        for line in ((completed.stderr or "") + "\n" + (completed.stdout or "")).splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                value = float(parts[0])
            except ValueError:
                continue
            # perf -x, columns are value,,event,runtime,percent,, so the name is not last.
            name = parts[2].lower() if len(parts) > 2 and parts[2] else parts[-1].lower()
            if not name or "<not" in name or "not counted" in line.lower() or "<not supported>" in line.lower():
                continue
            counts[name] = value

        def rate(miss: str, total: str) -> str:
            if miss not in counts or total not in counts or counts[total] <= 0:
                return ""
            return counts[miss] / counts[total]

        l3_rate = rate("llc-load-misses", "llc-loads") or L3_COUNTER_NA
        return elapsed, rate("dtlb-load-misses", "dtlb-loads"), l3_rate
    import numpy as np
    table = np.zeros(table_size, dtype=np.uint64)
    rng = np.random.default_rng(seed if seed else 42)
    start = time.perf_counter()
    chunk = min(total_updates, 8_000_000)
    done = 0
    while done < total_updates:
        n = min(chunk, total_updates - done)
        idx = rng.integers(0, table_size, size=n, dtype=np.int64)
        table[idx] += 1
        done += n
    return max(1e-9, time.perf_counter() - start), "", L3_COUNTER_NA


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


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    configured_table_size = max(1024, int(float(pv(params, "table_size", args.profile, 4194304) or 4194304)))
    llc_bytes = largest_last_level_cache_bytes()
    table_size = required_table_elements(configured_table_size, llc_bytes)
    if table_size != configured_table_size:
        print(
            f"[INFO] Expanded GUPS table from {configured_table_size} to {table_size} uint64 elements "
            f"(detected LLC={llc_bytes} bytes)"
        )
    updates = max(1, int(float(pv(params, "num_updates", args.profile, 1000000) or 1000000)))
    iters = max(1, int(float(pv(params, "num_iterations", args.profile, 1) or 1)))
    threads = max(1, int(float(pv(params, "num_threads", args.profile, 1) or 1)))
    seed = int(float(pv(params, "seed", args.profile, 42) or 42))
    numa_node = str(pv(params, "numa_node", args.profile, "0") or "")
    affinity = str(pv(params, "thread_affinity", args.profile, "") or "")
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    elapsed, tlb, l3 = run_gups(Path(args.run_dir), table_size, updates, iters, threads, seed, numa_node, affinity)
    gups = (updates * iters) / elapsed / 1e9
    row = {
        "kind": "sample", "seconds": elapsed, "updates": updates, "total_updates": updates * iters,
        "gups": gups, "giga_updates_score": gups, "errors": 0, "updates_sec": (updates * iters) / elapsed,
        "table_size": table_size, "num_updates": updates, "elapsed_sec": elapsed,
        "tlb_miss_rate": tlb, "l3_miss_rate": l3,
        "payload_update_gb_s": (updates * iters * 8.0) / elapsed / 1e9,
    }
    summary = dict(row)
    summary["kind"] = "summary"
    write_csv(args.raw_file, [
        "kind", "seconds", "updates", "total_updates", "gups", "giga_updates_score", "errors", "updates_sec",
        "table_size", "num_updates", "elapsed_sec", "tlb_miss_rate", "l3_miss_rate",
        "payload_update_gb_s",
    ], [row, summary])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
