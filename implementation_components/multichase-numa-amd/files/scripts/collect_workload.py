#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Harness wrapper that invokes overlay scripts/collect_multichase.py.
# Spec: working_set_size expands from yaml. stride, warmup, and iteration
# counts are forwarded. remote_dram is omitted when the host has one node.
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parent / "collect_multichase.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect multichase NUMA latency samples")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    parser.add_argument("--num-numa-nodes", default="1")
    parser.add_argument("--num-threads", default="1")
    parser.add_argument("--thread-affinity", default="")
    parser.add_argument("--page-size", default="4KB")
    parser.add_argument("--working-set-size", default="")
    parser.add_argument("--stride", default="64")
    parser.add_argument("--access-pattern", default="random")
    parser.add_argument("--prefetch-enabled", default="false")
    parser.add_argument("--warmup-iters", default="10000")
    parser.add_argument("--num-iterations", default="200000")
    args, _unknown = parser.parse_known_args()
    return args


def main() -> int:
    args = parse_args()
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    if not HELPER.is_file():
        raise SystemExit(f"[FAIL] missing overlay {HELPER.name}")
    cmd = [
        sys.executable,
        str(HELPER),
        "--output",
        args.raw_file,
        "--profile",
        args.profile,
        "--config",
        args.config,
        "--num-numa-nodes",
        str(args.num_numa_nodes),
        "--num-threads",
        str(args.num_threads),
        "--thread-affinity",
        str(args.thread_affinity),
        "--page-size",
        str(args.page_size),
        "--stride",
        str(args.stride),
        "--access-pattern",
        str(args.access_pattern),
        "--prefetch-enabled",
        str(args.prefetch_enabled),
        "--warmup-iters",
        str(args.warmup_iters),
        "--num-iterations",
        str(args.num_iterations),
    ]
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
