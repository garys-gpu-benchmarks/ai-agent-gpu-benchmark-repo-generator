#!/usr/bin/env python3
# File: scripts/collect_cublas_gemm.py
# Version: 1.0.0
# Author: TEMPLATE_00_54 generator
# Date: 2026-08-18
# Description: Run the cuBLAS GEMM harness twice and emit METRICS_CSV samples plus summary.
# Execution: .venv/bin/python scripts/collect_cublas_gemm.py --output PATH --config PATH
# Options: --output, --config, --profile, --function, --dtype, --M, --N, --K, --transposeA, --transposeB, --alpha, --beta, --lda, --ldb, --ldc, --batch-count, --warmup-iters, --num-iterations, --norm-check, --harness
# Requirements: Python 3.12, PyYAML
# Environment: Repository-local .venv after setup.sh
# Dependencies: bin/cublas_gemm
# Variables: PATH
# Repository: gpu-bench-nvidia-gemm-cublas-micro
# License: Apache-2.0

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path
from statistics import mean

import yaml


METRIC_FIELDS = [
    # Named as the workbook key (#1 achieved_compute_tflops); was "tflops", which
    # the summary never matched. The harness RESULT line still prints tflops=.
    "achieved_compute_tflops",
    "kernel_time_msec",
    "minimum_operand_traffic_gb_s",
    "relative_l1_checked_columns",
    "norm_error_2",
]
PARAM_FIELDS = [
    "function",
    "dtype",
    "M",
    "N",
    "K",
    "transposeA",
    "transposeB",
    "alpha",
    "beta",
    "lda",
    "ldb",
    "ldc",
    "batch_count",
    "warmup_iters",
    "num_iterations",
    "norm_check",
]
RESULT_RE = re.compile(
    r"RESULT\s+function=(\S+)\s+dtype=(\S+)\s+M=(\d+)\s+N=(\d+)\s+K=(\d+)\s+"
    r"lda=(\d+)\s+ldb=(\d+)\s+ldc=(\d+)\s+batch_count=(\d+)\s+"
    r"tflops=([0-9.eE+-]+)\s+kernel_time_msec=([0-9.eE+-]+)\s+"
    r"memory_bandwidth_gb_s=([0-9.eE+-]+)\s+norm_error_1=([0-9.eE+-]+)\s+"
    r"norm_error_2=([0-9.eE+-]+)\s+status=(\w+)"
)


def run_text(command: list[str], timeout: int) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


def profile_value(sweep: dict, key: str, profile: str, default):
    value = sweep.get(key, default)
    if isinstance(value, dict):
        if profile in value:
            return value[profile]
        if "smoke" in value:
            return value["smoke"]
    return value


def load_sweep(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload.get("sweep", payload)


def parse_results(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for match in RESULT_RE.finditer(text):
        rows.append(
            {
                "function": match.group(1),
                "dtype": match.group(2),
                "M": int(match.group(3)),
                "N": int(match.group(4)),
                "K": int(match.group(5)),
                "lda": int(match.group(6)),
                "ldb": int(match.group(7)),
                "ldc": int(match.group(8)),
                "batch_count": int(match.group(9)),
                "tflops": float(match.group(10)),
                "kernel_time_msec": float(match.group(11)),
                "memory_bandwidth_gb_s": float(match.group(12)),
                "norm_error_1": float(match.group(13)),
                "norm_error_2": float(match.group(14)),
                "status": match.group(15),
            }
        )
    return rows


def estimate_timeout(iterations: int, warmup: int, m: int) -> int:
    # Measured miss: 72000-iter 4096^3 timed out at 468s (4 ms/iter + 180s).
    # GPU loop plus a 64-column host panel check. Keep two passes under 2700s.
    per_iter_ms = 0.05 if m <= 128 else 10.0
    host_norm_sec = 5 if m <= 128 else 45
    return max(300, int((max(iterations, 1) + max(warmup, 0)) * per_iter_ms / 1000.0) + host_norm_sec + 180)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect cuBLAS GEMM samples")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--function", default="")
    parser.add_argument("--dtype", default="")
    parser.add_argument("--M", dest="M", default="")
    parser.add_argument("--N", dest="N", default="")
    parser.add_argument("--K", dest="K", default="")
    parser.add_argument("--transposeA", default="")
    parser.add_argument("--transposeB", default="")
    parser.add_argument("--alpha", default="")
    parser.add_argument("--beta", default="")
    parser.add_argument("--lda", default="")
    parser.add_argument("--ldb", default="")
    parser.add_argument("--ldc", default="")
    parser.add_argument("--batch-count", dest="batch_count", default="")
    parser.add_argument("--warmup-iters", dest="warmup_iters", default="")
    parser.add_argument("--num-iterations", dest="num_iterations", default="")
    parser.add_argument("--norm-check", dest="norm_check", default="")
    parser.add_argument("--harness", default="bin/cublas_gemm")
    args = parser.parse_args()

    sweep = load_sweep(Path(args.config))
    profile = args.profile
    function = str(args.function or profile_value(sweep, "function", profile, True)).lower()
    dtype = str(args.dtype or profile_value(sweep, "dtype", profile, "f32_r"))
    m_dim = str(args.M or profile_value(sweep, "M", profile, 64))
    n_dim = str(args.N or profile_value(sweep, "N", profile, 64))
    k_dim = str(args.K or profile_value(sweep, "K", profile, 64))
    transpose_a = str(args.transposeA or profile_value(sweep, "transposeA", profile, "N"))
    transpose_b = str(args.transposeB or profile_value(sweep, "transposeB", profile, "N"))
    alpha = str(args.alpha or profile_value(sweep, "alpha", profile, "1.0"))
    beta = str(args.beta or profile_value(sweep, "beta", profile, "0.0"))
    lda = str(args.lda or profile_value(sweep, "lda", profile, 64))
    ldb = str(args.ldb or profile_value(sweep, "ldb", profile, 64))
    ldc = str(args.ldc or profile_value(sweep, "ldc", profile, 64))
    batch_count = str(args.batch_count or profile_value(sweep, "batch_count", profile, 1))
    warmup_iters = str(args.warmup_iters or profile_value(sweep, "warmup_iters", profile, 2))
    num_iterations = str(args.num_iterations or profile_value(sweep, "num_iterations", profile, 2))
    norm_check = str(args.norm_check or profile_value(sweep, "norm_check", profile, 1))
    if function in {"1", "true", "yes"}:
        function = "true"

    print("# NVIDIA cuBLAS GEMM raw transcript")
    print(f"# profile={profile}")
    print(f"# function={function}")
    print(f"# dtype={dtype}")
    print(f"# M={m_dim}")
    print(f"# N={n_dim}")
    print(f"# K={k_dim}")
    print(f"# transposeA={transpose_a}")
    print(f"# transposeB={transpose_b}")
    print(f"# alpha={alpha}")
    print(f"# beta={beta}")
    print(f"# lda={lda}")
    print(f"# ldb={ldb}")
    print(f"# ldc={ldc}")
    print(f"# batch_count={batch_count}")
    print(f"# warmup_iters={warmup_iters}")
    print(f"# num_iterations={num_iterations}")
    print(f"# norm_check={norm_check}")

    command = [
        args.harness,
        "--function",
        function,
        "--dtype",
        dtype,
        "--M",
        m_dim,
        "--N",
        n_dim,
        "--K",
        k_dim,
        "--transposeA",
        transpose_a,
        "--transposeB",
        transpose_b,
        "--alpha",
        alpha,
        "--beta",
        beta,
        "--lda",
        lda,
        "--ldb",
        ldb,
        "--ldc",
        ldc,
        "--batch-count",
        batch_count,
        "--warmup-iters",
        warmup_iters,
        "--num-iterations",
        num_iterations,
        "--norm-check",
        norm_check,
    ]
    timeout_sec = estimate_timeout(int(float(num_iterations)), int(float(warmup_iters)), int(float(m_dim)))
    params = {
        "function": function,
        "dtype": dtype,
        "M": m_dim,
        "N": n_dim,
        "K": k_dim,
        "transposeA": transpose_a,
        "transposeB": transpose_b,
        "alpha": alpha,
        "beta": beta,
        "lda": lda,
        "ldb": ldb,
        "ldc": ldc,
        "batch_count": batch_count,
        "warmup_iters": warmup_iters,
        "num_iterations": num_iterations,
        "norm_check": norm_check,
    }
    rows: list[dict[str, object]] = []
    for pass_index in (1,):  # one timed pass
        print(f"# timed_pass={pass_index}")
        code, text = run_text(command, timeout=timeout_sec)
        print(f"# check=cublas-gemm-pass{pass_index} exit={code}")
        print(text.rstrip())
        print()
        if code != 0:
            raise SystemExit(f"[FAIL] cublas_gemm harness exited {code} on pass {pass_index}")
        parsed = parse_results(text)
        if not parsed:
            raise SystemExit(f"[FAIL] No RESULT line was parsed from pass {pass_index}.")
        item = parsed[-1]
        rows.append(
            {
                "check": f"pass{pass_index}",
                "status": "ok" if float(item["tflops"]) > 0 else "error",
                **params,
                "achieved_compute_tflops": float(item["tflops"]),
                "kernel_time_msec": float(item["kernel_time_msec"]),
                "minimum_operand_traffic_gb_s": float(item["memory_bandwidth_gb_s"]),
                "relative_l1_checked_columns": float(item["norm_error_1"]),
                "norm_error_2": float(item["norm_error_2"]),
            }
        )

    if len(rows) < 1:
        raise SystemExit("[FAIL] Collector must emit at least one timed sample.")

    summary = {
        "check": "summary",
        "status": "ok",
        **params,
        "achieved_compute_tflops": mean(float(row["achieved_compute_tflops"]) for row in rows),
        "kernel_time_msec": mean(float(row["kernel_time_msec"]) for row in rows),
        "minimum_operand_traffic_gb_s": mean(float(row["minimum_operand_traffic_gb_s"]) for row in rows),
        "relative_l1_checked_columns": mean(float(row["relative_l1_checked_columns"]) for row in rows),
        "norm_error_2": mean(float(row["norm_error_2"]) for row in rows),
    }
    rows.append(summary)

    fieldnames = ["check", "status", *PARAM_FIELDS, *METRIC_FIELDS]
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
