#!/usr/bin/env python3
# File: scripts/collect_numa_cache.py
# Version: 1.0.0
# Author: TEMPLATE_00_54 generator
# Date: 2026-08-19
# Description: Sweep dependent pointer-chase working sets across local and remote NUMA targets and emit METRICS_CSV.
# Execution: .venv/bin/python scripts/collect_numa_cache.py --output PATH --config PATH
# Options: --output, --config, --profile, --source-numa-node, --num-threads, --thread-affinity, --page-size, --stride, --access-pattern, --num-iterations
# Requirements: Python 3.12, PyYAML, cmake, g++, numactl, bin/numa_sweep
# Environment: Repository-local .venv after setup.sh
# Dependencies: scripts/build.sh, src/numa_sweep.cpp, config/benchmark_config.yaml
# Variables: none
# Repository: sys-bench-nvidia-numa-cache-performance
# License: Apache-2.0

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml


METRIC_FIELDS = [
    "cache_latency_nsec",
    "local_numa_node_latency_nsec",
    "remote_numa_node_latency_nsec",
    "cross_socket_numa_penalty_ratio",
    "local_dram_pointer_chase_bandwidth_gb_s",
    "cache_miss_counters_misses_sec",
]
NA_PERF_COUNTER = "na (expected: perf_event_paranoid blocks cache-misses)"
NA_REMOTE_NUMA = "na (expected: numactl policy not permitted; second numa node not measurable)"
PARAM_FIELDS = [
    "check",
    "source_numa_node",
    "target_numa_node",
    "num_threads",
    "thread_affinity",
    "page_size",
    "working_set_size",
    "cache_level",
    "access_pattern",
    "stride",
    "num_iterations",
    "status",
]
NS_RE = re.compile(r"ns/access\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
BW_RE = re.compile(r"bandwidth_gb_s\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
MISS_RE = re.compile(r"^\s*([0-9][0-9,]*)\s+cache-misses", re.IGNORECASE | re.MULTILINE)
ELAPSED_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s+seconds time elapsed", re.IGNORECASE)


def pick(sweep: dict, key: str, profile: str, default: str = "") -> str:
    value = sweep.get(key, default)
    if isinstance(value, dict):
        value = value.get(profile, value.get("smoke", default))
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value).strip()


def load_sweep(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload.get("sweep", payload)


def split_csv_list(value: str) -> list[str]:
    items = []
    for part in str(value).replace(";", ",").split(","):
        item = part.strip()
        if item:
            items.append(item)
    return items


def infer_cache_level(size: int) -> str:
    if size <= 65536:
        return "L1"
    if size <= 524288:
        return "L2"
    if size <= 8388608:
        return "L3"
    return "DRAM"


def parse_size_bytes(value: str) -> int:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)i?b?\s*", value, re.I)
    if match is None:
        return 0
    scale = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    return int(float(match.group(1)) * scale[match.group(2).lower()])


def largest_last_level_cache_bytes() -> int:
    """Largest unified/data cache visible to one CPU, not the sum over CPUs."""
    largest = 0
    for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cache/index*"):
        try:
            cache_type = (path / "type").read_text(encoding="utf-8").strip().lower()
            level = int((path / "level").read_text(encoding="utf-8").strip())
            size = parse_size_bytes((path / "size").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if cache_type in {"data", "unified"} and level >= 3:
            largest = max(largest, size)
    return largest


def summary_indices(sizes: list[int], levels: list[str]) -> tuple[int, int]:
    """Select the largest configured cache tier and the configured DRAM tier."""
    named = [levels[i] if i < len(levels) else infer_cache_level(size) for i, size in enumerate(sizes)]
    dram_candidates = [i for i, level in enumerate(named) if "dram" in level.lower()]
    dram_index = max(dram_candidates, key=lambda i: sizes[i]) if dram_candidates else max(
        range(len(sizes)), key=lambda i: sizes[i]
    )
    cache_candidates = [i for i, level in enumerate(named) if "dram" not in level.lower()]
    cache_index = max(cache_candidates, key=lambda i: sizes[i]) if cache_candidates else dram_index
    return cache_index, dram_index


def run_command(command: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        return completed.returncode, completed.stdout
    except FileNotFoundError as exc:
        return 127, str(exc)


def parse_ns_per_access(text: str) -> float | None:
    match = NS_RE.search(text)
    if match is None:
        return None
    return float(match.group(1))


def parse_bandwidth(text: str) -> float | None:
    match = BW_RE.search(text)
    if match is None:
        return None
    return float(match.group(1))


def parse_cache_misses_per_sec(text: str) -> float | str:
    miss_match = MISS_RE.search(text)
    elapsed_match = ELAPSED_RE.search(text)
    if miss_match is None:
        return NA_PERF_COUNTER
    misses = float(miss_match.group(1).replace(",", ""))
    elapsed = float(elapsed_match.group(1)) if elapsed_match is not None else 0.0
    if elapsed <= 0.0:
        return "na (perf elapsed time unavailable)"
    return misses / elapsed


def list_numa_nodes() -> list[int]:
    nodes: list[int] = []
    code, text = run_command(["numactl", "--hardware"])
    match = re.search(r"available:\s*(\d+)\s*nodes\s*\(([^)]+)\)", text)
    if code == 0 and match:
        span = match.group(2)
        for token in re.split(r"[,\s]+", span.replace("-", " ")):
            if token.isdigit():
                nodes.append(int(token))
        if "-" in span and len(nodes) >= 2:
            low, high = nodes[0], nodes[-1]
            nodes = list(range(low, high + 1))
    node_root = Path("/sys/devices/system/node")
    if not nodes and node_root.is_dir():
        for path in sorted(node_root.glob("node[0-9]*")):
            nodes.append(int(path.name[4:]))
    return nodes or [0]


def resolve_remote_node(source: int, nodes: list[int]) -> int:
    for node in nodes:
        if node != source:
            return node
    return source


def resolve_perf_binary() -> str:
    """Prefer a kernel-matched perf. /usr/bin/perf is a stub on some Ubuntu hosts."""
    kernel = os.uname().release if hasattr(os, "uname") else ""
    candidates = []
    if kernel:
        candidates.append(Path(f"/usr/lib/linux-tools/{kernel}/perf"))
        candidates.append(Path(f"/usr/lib/linux-tools-{kernel}/perf"))
    lib = Path("/usr/lib")
    if lib.is_dir():
        for path in sorted(lib.glob("linux-tools-*/perf")):
            candidates.append(path)
    which = shutil.which("perf")
    if which:
        candidates.append(Path(which))
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size > 10000:
                return str(path)
        except OSError:
            continue
    return which or ""


def perf_permission_denied(text: str, code: int) -> bool:
    lowered = text.lower()
    return (
        code in {255, 1, 2}
        and (
            "no permission to enable" in lowered
            or "not supported" in lowered
            or "permission denied" in lowered
            or "perf_event_paranoid" in lowered
        )
    )


def launch_sweep(
    binary: Path,
    extra_args: list[str],
    cpu_node: str,
    mem_node: str,
    env: dict[str, str],
    use_perf: bool,
    perf_bin: str = "perf",
) -> tuple[int, str, list[str], bool, bool]:
    official = [
        "numactl",
        f"--cpunodebind={cpu_node}",
        f"--membind={mem_node}",
        str(binary),
        *extra_args,
    ]
    fallbacks = [
        official,
        ["numactl", f"--cpunodebind={cpu_node}", str(binary), *extra_args],
        [str(binary), *extra_args],
    ]
    code = 1
    text = ""
    used = official
    perf_enabled = use_perf
    for command in fallbacks:
        launch = [perf_bin, "stat", "-e", "cache-misses", "--", *command] if perf_enabled else command
        print("[RUN] " + " ".join(launch))
        code, text = run_command(launch, env)
        print(f"# numa_sweep_exit={code}")
        print(text.rstrip())
        print()
        used = launch
        if perf_enabled and perf_permission_denied(text, code):
            print("# INFO perf cache-misses is not permitted; retrying without perf")
            perf_enabled = False
            launch = command
            print("[RUN] " + " ".join(launch))
            code, text = run_command(launch, env)
            print(f"# numa_sweep_exit={code}")
            print(text.rstrip())
            print()
            used = launch
        if code == 0 and parse_ns_per_access(text) is not None:
            break
        if (
            "Operation not permitted" in text
            or "does not support NUMA policy" in text
            or "membind" in text.lower()
            or code == 127
        ):
            print("# INFO numactl policy not permitted in this container; trying a fallback launch")
            continue
        break
    membind_ok = code == 0 and any(part.startswith("--membind=") for part in used)
    return code, text, used, perf_enabled, membind_ok


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()



def _fmt6(value):
    """6-decimal string, or blank for a value that was not measured."""
    if value is None or value == "":
        return ""
    if str(value).startswith("na ("):
        return str(value)
    return f"{float(value):.6f}"

def main() -> int:
    parser = argparse.ArgumentParser(description="Collect NUMA cache latency samples")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--source-numa-node", default="")
    parser.add_argument("--num-threads", default="")
    parser.add_argument("--thread-affinity", default="")
    parser.add_argument("--page-size", default="")
    parser.add_argument("--stride", default="")
    parser.add_argument("--access-pattern", default="")
    parser.add_argument("--num-iterations", default="")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    sweep = load_sweep(Path(args.config))
    profile = args.profile
    source_numa_node = args.source_numa_node or pick(sweep, "source_numa_node", profile, "0")
    target_spec = pick(sweep, "target_numa_node", profile, "0,remote")
    num_threads = args.num_threads or pick(sweep, "num_threads", profile, "1")
    thread_affinity = args.thread_affinity or pick(sweep, "thread_affinity", profile, "strict")
    page_size = args.page_size or pick(sweep, "page_size", profile, "4KB")
    working_set = pick(sweep, "working_set_size", profile, "32768,2097152,268435456")
    cache_level_spec = pick(sweep, "cache_level", profile, "L1,L3,DRAM")
    stride = args.stride or pick(sweep, "stride", profile, "64")
    access_pattern = args.access_pattern or pick(sweep, "access_pattern", profile, "random")
    num_iterations = args.num_iterations or pick(sweep, "num_iterations", profile, "20000")

    sizes = [int(item) for item in split_csv_list(working_set)]
    levels = split_csv_list(cache_level_spec)
    targets = split_csv_list(target_spec)
    if not sizes or not targets:
        raise SystemExit("[FAIL] working_set_size and target_numa_node must expand to at least one case.")
    cache_index, dram_index = summary_indices(sizes, levels)
    requested_dram_size = sizes[dram_index]
    llc_bytes = largest_last_level_cache_bytes()
    minimum_dram_size = max(256 * 1024**2, 2 * llc_bytes)
    sizes[dram_index] = max(requested_dram_size, minimum_dram_size)
    if sizes[dram_index] != requested_dram_size:
        print(
            f"# INFO expanded DRAM working set from {requested_dram_size} to {sizes[dram_index]} bytes "
            f"(detected LLC={llc_bytes} bytes)"
        )
    dram_size = sizes[dram_index]
    cache_size = sizes[cache_index]

    print("# numa_sweep dependent pointer-chase raw transcript")
    print(f"# profile={profile}")
    print(f"# source_numa_node={source_numa_node}")
    print(f"# target_numa_node={target_spec}")
    print(f"# num_threads={num_threads}")
    print(f"# thread_affinity={thread_affinity}")
    print(f"# page_size={page_size}")
    print(f"# working_set_size={working_set}")
    print(f"# cache_level={cache_level_spec}")
    print(f"# stride={stride}")
    print(f"# access_pattern={access_pattern}")
    print(f"# num_iterations={num_iterations}")

    binary = repo_root / "bin" / "numa_sweep"
    if not binary.is_file() and (repo_root / "bin" / "numa_sweep.exe").is_file():
        binary = repo_root / "bin" / "numa_sweep.exe"
    if not binary.is_file():
        build_cmd = ["bash", str(repo_root / "scripts" / "build.sh")]
        print("[RUN] " + " ".join(build_cmd))
        build = subprocess.run(
            build_cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=repo_root,
        )
        print(build.stdout.rstrip())
        if build.returncode != 0 or not binary.is_file():
            raise SystemExit("[FAIL] numa_sweep compile failed.")

    nodes = list_numa_nodes()
    source_node = int(float(source_numa_node))
    remote_node = resolve_remote_node(source_node, nodes)
    if remote_node == source_node:
        print("# INFO only one NUMA node is visible so remote may equal local")
    perf_bin = resolve_perf_binary()
    use_perf = bool(perf_bin)
    if use_perf:
        probe_code, probe_text = run_command([perf_bin, "stat", "-e", "cache-misses", "--", "/bin/true"])
        if probe_code != 0 and perf_permission_denied(probe_text, probe_code):
            print("# INFO perf cache-misses is not permitted")
            use_perf = False
    if not use_perf:
        print("# INFO perf is unavailable")

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(num_threads)
    if thread_affinity.lower() == "strict":
        env["OMP_PROC_BIND"] = "true"
        env["OMP_PLACES"] = "cores"

    measured: dict[tuple[int, str], dict[str, object]] = {}
    extra_args_base = {
        "stride": str(stride),
        "iters": str(num_iterations),
        "threads": str(num_threads),
        "pattern": str(access_pattern),
    }
    for size in sizes:
        for target_token in targets:
            mem_node = remote_node if target_token.lower() == "remote" else int(float(target_token))
            extra_args = [
                "--size",
                str(size),
                "--stride",
                extra_args_base["stride"],
                "--iters",
                extra_args_base["iters"],
                "--threads",
                extra_args_base["threads"],
                "--pattern",
                extra_args_base["pattern"],
            ]
            print(f"# target={target_token} size={size} cpunodebind={source_node} membind={mem_node}")
            code, text, _used, perf_enabled, membind_ok = launch_sweep(
                binary,
                extra_args,
                str(source_node),
                str(mem_node),
                env,
                use_perf,
                perf_bin or "perf",
            )
            if not perf_enabled:
                use_perf = False
            ns_value = parse_ns_per_access(text)
            bw_value = parse_bandwidth(text)
            if code != 0 or ns_value is None or bw_value is None:
                raise SystemExit(f"[FAIL] numa_sweep target {target_token} size {size} did not report ns/access and bandwidth.")
            measured[(size, target_token)] = {
                "latency": ns_value,
                "bandwidth": bw_value,
                "misses": (
                    parse_cache_misses_per_sec(text)
                    if perf_enabled
                    else NA_PERF_COUNTER
                ),
                "membind_ok": membind_ok,
            }

    local_key = next((token for token in targets if token.lower() != "remote"), targets[0])
    remote_key = next((token for token in targets if token.lower() == "remote"), None)

    def level_for(index: int, size: int) -> str:
        return levels[index] if index < len(levels) else infer_cache_level(size)

    cache_measurement = measured[(cache_size, local_key)]
    dram_measurement = measured[(dram_size, local_key)]
    cache_ns = cache_measurement["latency"]
    dram_ns = dram_measurement["latency"]
    dram_bw = dram_measurement["bandwidth"]
    dram_misses = dram_measurement["misses"]
    remote_ns = NA_REMOTE_NUMA
    ratio = NA_REMOTE_NUMA
    if remote_key is not None and remote_node != source_node:
        remote_measurement = measured[(dram_size, remote_key)]
        if remote_measurement["membind_ok"]:
            remote_ns = remote_measurement["latency"]
            ratio = remote_ns / dram_ns if dram_ns > 0 else None
    summary_metrics = {
        "cache_latency_nsec": cache_ns,
        "local_numa_node_latency_nsec": dram_ns,
        "remote_numa_node_latency_nsec": remote_ns,
        "cross_socket_numa_penalty_ratio": ratio,
        "local_dram_pointer_chase_bandwidth_gb_s": dram_bw,
        "cache_miss_counters_misses_sec": dram_misses,
    }

    per_size: list[dict[str, str]] = []
    for index, size in enumerate(sizes):
        level = level_for(index, size)
        local_meas = measured[(size, local_key)]
        per_size.append({
            "working_set_size": str(size),
            "cache_level": level,
            "access_pattern": access_pattern,
            "latency_nsec": _fmt6(local_meas["latency"]),
            "bandwidth_gb_sec": _fmt6(local_meas["bandwidth"]),
            "cache_misses_per_sec": _fmt6(local_meas["misses"]),
        })
    write_csv(Path(args.output).parent / "per_size.csv", [
        "working_set_size", "cache_level", "access_pattern", "latency_nsec", "bandwidth_gb_sec",
        "cache_misses_per_sec",
    ], per_size)

    def summary_row(check: str) -> dict[str, str]:
        return {
            "check": check,
            "source_numa_node": str(source_node),
            "target_numa_node": target_spec,
            "num_threads": num_threads,
            "thread_affinity": thread_affinity,
            "page_size": page_size,
            "working_set_size": str(dram_size),
            "cache_level": "DRAM",
            "access_pattern": access_pattern,
            "stride": stride,
            "num_iterations": num_iterations,
            "status": "ok",
            **{name: _fmt6(summary_metrics[name]) for name in METRIC_FIELDS},
        }

    rows = [summary_row("summary"), summary_row("summary_repeat")]

    fieldnames = [*PARAM_FIELDS, *METRIC_FIELDS]
    output_path = Path(args.output)
    write_csv(output_path, fieldnames, rows)
    raw_output = output_path.parent / "raw_output.csv"
    write_csv(raw_output, fieldnames, rows)
    print("# METRICS_CSV")
    with output_path.open(encoding="utf-8") as handle:
        print(handle.read(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
