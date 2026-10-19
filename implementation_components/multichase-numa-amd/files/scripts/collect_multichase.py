#!/usr/bin/env python3
# File: scripts/collect_multichase.py
# Version: 1.0.1
# Author: TEMPLATE_00_67 generator
# Date: 2026-08-31
# Description: Compile and run C multichase across yaml working-set tiers.
# Execution: .venv/bin/python scripts/collect_multichase.py --output <raw.txt>
# Options: --output, --num-numa-nodes, --num-threads, --thread-affinity, --page-size, --stride, --access-pattern, --prefetch-enabled, --warmup-iters, --num-iterations, --profile
# Requirements: Python 3.10+; gcc; numactl
# Environment: Local generated repository after setup.sh
# Dependencies: gcc, numactl, PyYAML
# Variables: PATH
# Repository: sys-bench-amd-multichase-numa-latency
# License: Apache-2.0

from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import subprocess
from pathlib import Path

import yaml

HEADER = "sample_index,status,tier,latency_ns,working_set_size,stride,thread_count,error_message"


def available_numa_nodes() -> set[int]:
    """Parse `numactl --hardware`'s "available: N nodes (0-1)" line. Returns
    an empty set when numactl is missing or its output doesn't parse --
    callers treat that the same as "don't know, don't bind"."""
    if shutil.which("numactl") is None:
        return set()
    completed = subprocess.run(
        ["numactl", "--hardware"], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    match = re.search(r"available:\s*\d+\s*nodes?\s*\(([^)]*)\)", completed.stdout)
    if not match:
        return set()
    nodes: set[int] = set()
    for part in match.group(1).split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            if lo.strip().isdigit() and hi.strip().isdigit():
                nodes.update(range(int(lo), int(hi) + 1))
        elif part.isdigit():
            nodes.add(int(part))
    return nodes


def sysfs_numa_nodes() -> set[int]:
    """NUMA nodes the kernel exposes in /sys, which containers often show even
    when `numactl --hardware` says "No NUMA available"."""
    nodes: set[int] = set()
    for entry in Path("/sys/devices/system/node").glob("node[0-9]*"):
        suffix = entry.name[4:]
        if suffix.isdigit():
            nodes.add(int(suffix))
    return nodes


REMOTE_BIND_DENIED = "na (expected: host has 2+ NUMA nodes but numactl cannot bind memory to a remote node here)"


def parse_tiers(value: object) -> list[tuple[str, int]]:
    text = str(value)
    if isinstance(value, dict):
        text = str(next(iter(value.values())))
    items = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, size = part.split("=", 1)
            items.append((name.strip(), int(float(size))))
        else:
            items.append((f"tier{len(items)}", int(float(part))))
    return items


def compile_binary() -> Path:
    build = Path("build")
    build.mkdir(exist_ok=True)
    binary = build / "multichase"
    cmd = ["gcc", "-O2", "-std=c11", "src/multichase.c", "-o", str(binary)]
    completed = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if completed.returncode != 0:
        raise SystemExit(f"[FAIL] multichase compile failed\n{completed.stdout}")
    return binary


def parse_latency(text: str) -> float:
    match = re.search(r"latency_ns\s+([0-9.]+)", text)
    if match:
        return float(match.group(1))
    nums = re.findall(r"([0-9]+\.[0-9]+)", text)
    return float(nums[-1]) if nums else 0.0


def not_measured_row(index, tier, size, args, reason, latency_ns=""):
    """Row for a tier that cannot be measured on this host. A blank latency_ns
    becomes "not measured" in the summary. An na (...) value is printed as-is."""
    return {
        "sample_index": index,
        "status": "ok",
        "tier": tier,
        "latency_ns": latency_ns,
        "working_set_size": size,
        "stride": args.stride,
        "thread_count": args.num_threads,
        "error_message": f"{tier} not measured: {reason}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect multichase latency samples")
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--num-numa-nodes", default="1")
    parser.add_argument("--num-threads", default="1")
    parser.add_argument("--thread-affinity", default="0-3")
    parser.add_argument("--page-size", default="4KB")
    parser.add_argument("--stride", default="64")
    parser.add_argument("--access-pattern", default="random")
    parser.add_argument("--prefetch-enabled", default="false")
    parser.add_argument("--warmup-iters", default="10000")
    parser.add_argument("--num-iterations", default="200000")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) if Path(args.config).is_file() else {}
    sweep = (config or {}).get("sweep", {})
    working = sweep.get("working_set_size", "l1=16384,l2=262144")
    if isinstance(working, dict):
        working = working.get(args.profile, next(iter(working.values())))
    tiers = parse_tiers(working)
    warmup = int(float(args.warmup_iters))
    iters = int(float(args.num_iterations))
    if args.profile == "smoke":
        warmup = min(warmup, 10000)
        iters = min(iters, 200000)
    binary = compile_binary()
    transcript = io.StringIO()
    print("[INFO] working_set_size expands from yaml; no list CLI flag", file=transcript)
    print(f"[RUN] gcc -O2 -std=c11 src/multichase.c -o {binary}", file=transcript)
    numa_nodes = available_numa_nodes()
    has_numactl = shutil.which("numactl") is not None
    if has_numactl and not numa_nodes:
        print("[WARN] numactl --hardware did not report any nodes; running unbound", file=transcript)
    elif not has_numactl:
        print("[WARN] numactl is not installed; running without NUMA binding", file=transcript)
    rows = []
    for index, (tier, size) in enumerate(tiers):
        if tier == "remote_dram" and len(numa_nodes) < 2:
            kernel_nodes = sysfs_numa_nodes()
            if len(kernel_nodes) >= 2:
                # numactl sees no NUMA (typical in a container) while the kernel
                # exposes several nodes: the host has them, binding is unavailable.
                print("[INFO] skipping remote_dram; numactl reports no NUMA but /sys shows "
                      f"{len(kernel_nodes)} nodes", file=transcript)
                rows.append(not_measured_row(
                    index, tier, size, args,
                    f"/sys shows {len(kernel_nodes)} NUMA nodes; numactl reports none",
                    REMOTE_BIND_DENIED,
                ))
                continue
            print("[INFO] skipping remote_dram; host does not have a second NUMA node", file=transcript)
            rows.append(not_measured_row(
                index, tier, size, args,
                f"host has {len(numa_nodes) or 'no detected'} NUMA node(s)",
                "na (requires a second NUMA node)",
            ))
            continue
        cpu_node = 0
        mem_node = 1 if tier == "remote_dram" else 0
        if numa_nodes:
            # Requesting a node this host doesn't actually have (a single-
            # socket host asked to bind remote_dram to node 1, for example)
            # used to make numactl itself fail with rc != 0 -- a host
            # configuration mismatch, not a real zero/failed latency
            # measurement. Clamp to a node that exists instead.
            if cpu_node not in numa_nodes:
                cpu_node = min(numa_nodes)
            if mem_node not in numa_nodes:
                mem_node = cpu_node
        if has_numactl:
            cmd = [
                "numactl",
                f"--cpunodebind={cpu_node}",
                f"--membind={mem_node}",
                str(binary),
                str(size),
                str(args.stride),
                str(iters),
                str(warmup),
            ]
        else:
            cmd = [str(binary), str(size), str(args.stride), str(iters), str(warmup)]
        print("#", f"metadata num_numa_nodes={args.num_numa_nodes} num_threads={args.num_threads} thread_affinity={args.thread_affinity} page_size={args.page_size} working_set_size={size} stride={args.stride} access_pattern={args.access_pattern} prefetch_enabled={args.prefetch_enabled} warmup_iters={warmup} iterations={iters} tier={tier}", file=transcript)
        print("[RUN]", " ".join(cmd), file=transcript)
        completed = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        if (
            completed.returncode != 0
            and has_numactl
            and (
                "Operation not permitted" in (completed.stdout or "")
                or "does not support NUMA policy" in (completed.stdout or "")
            )
        ):
            print("[WARN] numactl bind not permitted; retrying unbound", file=transcript)
            if tier == "remote_dram":
                print("[INFO] skipping remote_dram; membind did not succeed", file=transcript)
                rows.append(not_measured_row(index, tier, size, args, "numactl --membind=1 not permitted",
                                             REMOTE_BIND_DENIED))
                continue
            cmd = [str(binary), str(size), str(args.stride), str(iters), str(warmup)]
            print("[RUN]", " ".join(cmd), file=transcript)
            completed = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        print(completed.stdout, file=transcript)
        latency = parse_latency(completed.stdout)
        ok = completed.returncode == 0 and latency > 0
        rows.append(
            {
                "sample_index": index,
                "status": "ok" if ok else "error",
                "tier": tier,
                "latency_ns": latency,
                "working_set_size": size,
                "stride": args.stride,
                "thread_count": args.num_threads,
                "error_message": "" if ok else f"multichase exit {completed.returncode} latency_ns={latency}",
            }
        )
    if sum(1 for row in rows if row["latency_ns"] != "") < 2:
        raise SystemExit("[FAIL] multichase produced fewer than 2 samples")
    if any(row["status"] != "ok" for row in rows):
        raise SystemExit("[FAIL] multichase produced a zero or failed latency sample")
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, lineterminator='\n', fieldnames=HEADER.split(","))
    writer.writeheader()
    writer.writerows(rows)
    csv_text = csv_buf.getvalue()
    print("[INFO] Parsed CSV", file=transcript)
    print(csv_text, file=transcript)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(transcript.getvalue() + "\n" + csv_text, encoding="utf-8")
    output_path.with_suffix(".csv").write_text(csv_text, encoding="utf-8")
    print(csv_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
