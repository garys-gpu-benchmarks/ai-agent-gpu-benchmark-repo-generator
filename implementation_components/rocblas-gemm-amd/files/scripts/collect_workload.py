#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: rocBLAS GEMM microbenchmark (117/317). Runs the repository-local
#              rocblas-bench built by scripts/build.sh (rocm_compile_rocblas_bench)
#              for the yaml GEMM shape and writes one CSV row from its output.
#              Before 2026-10-01 this timed torch.matmul and wrote it under
#              rocblas-bench-like column names; rocblas-bench was built but never run.
from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import subprocess
from pathlib import Path

import yaml

STAGING = Path("third_party/rocBLAS/build/release/clients/staging")
NA_NO_NORM_CHECK = "na (norm_check is 0)"
HEADER = [
    "sample_index", "status", "function", "dtype", "transposeA", "transposeB",
    "M", "N", "K", "lda", "ldb", "ldc", "batch_count", "cold_iters", "hot_iters",
    "rocblas_gflops", "rocblas_gemm_us", "cpu_gflops", "norm_error_1",
    "achieved_compute_tflops", "kernel_time_msec", "minimum_operand_traffic_gb_s",
    "relative_l1_checked_columns", "error_message",
]


def element_bytes(dtype: str) -> int:
    key = dtype.lower()
    if key in {"f64_r", "f64", "fp64", "d"}:
        return 8
    if key in {"f16_r", "f16", "fp16", "h", "bf16_r", "bf16", "bf16_r"}:
        return 2
    if key in {"i8_r", "i8"}:
        return 1
    return 4


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def load_params(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return cfg.get("sweep") or {}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    return parser.parse_args()


def find_rocblas_bench() -> str | None:
    candidates = [os.environ.get("ROCBLAS_BENCH", ""), str(STAGING / "rocblas-bench"), shutil.which("rocblas-bench") or ""]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def parse_bench_output(text: str) -> dict[str, str]:
    """rocblas-bench prints a CSV header containing 'rocblas-Gflops' followed by
    one data row. Column sets differ between rocBLAS versions and with -v, so
    values are looked up by header name."""
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if "rocblas-Gflops" not in line or "," not in line:
            continue
        names = [cell.strip() for cell in line.split(",")]
        for data in lines[index + 1:]:
            if not data:
                continue
            cells = [cell.strip() for cell in data.split(",")]
            if len(cells) == len(names):
                return dict(zip(names, cells))
            break
    return {}


def number(value: str) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    def get(key, default):
        value = pv(params, key, args.profile, default)
        return default if value in ("", None) else value

    dtype = str(get("dtype", "f32_r"))
    m, n, k = (int(float(get(key, 64))) for key in ("M", "N", "K"))
    trans_a = str(get("transposeA", "N")).upper()[:1]
    trans_b = str(get("transposeB", "N")).upper()[:1]
    alpha, beta = str(get("alpha", 1)), str(get("beta", 0))
    lda = int(float(get("lda", m if trans_a == "N" else k)))
    ldb = int(float(get("ldb", k if trans_b == "N" else n)))
    ldc = int(float(get("ldc", m)))
    batch_count = max(1, int(float(get("batch_count", 1))))
    cold_iters = max(0, int(float(get("warmup_iters", 2))))
    hot_iters = max(1, int(float(get("num_iterations", 2))))
    norm_check = str(get("norm_check", 1)).strip().lower() in {"1", "true", "yes"}
    function = "gemm_strided_batched" if batch_count > 1 else "gemm"

    bench = find_rocblas_bench()
    if bench is None and Path("scripts/build.sh").is_file():
        subprocess.run(["bash", "scripts/build.sh"], check=False)
        bench = find_rocblas_bench()
    if bench is None:
        raise SystemExit(f"[FAIL] rocblas-bench not found ({STAGING}/rocblas-bench); run bash scripts/build.sh")

    # warmup_iters -> --cold_iters and norm_check -> -v (rocblas-bench has no -w / --norm_check).
    cmd = [
        bench, "-f", function, "-r", dtype,
        "--transposeA", trans_a, "--transposeB", trans_b,
        "-m", str(m), "-n", str(n), "-k", str(k),
        "--alpha", alpha, "--beta", beta,
        "--lda", str(lda), "--ldb", str(ldb), "--ldc", str(ldc),
        "--cold_iters", str(cold_iters), "-i", str(hot_iters),
        "-v", "1" if norm_check else "0",
    ]
    if batch_count > 1:
        cmd += ["--batch_count", str(batch_count)]
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/opt/rocm/lib:/opt/rocm/lib64:" + env.get("LD_LIBRARY_PATH", "")
    print("[RUN] " + " ".join(cmd))
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env, timeout=24 * 3600)
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    (run_dir / "rocblas_bench.txt").write_text(" ".join(cmd) + "\n" + text, encoding="utf-8")
    print(text.rstrip())
    values = parse_bench_output(text)
    gflops = number(values.get("rocblas-Gflops", ""))
    gemm_us = number(values.get("us", ""))
    if completed.returncode != 0 or gflops is None or gemm_us is None:
        raise SystemExit(f"[FAIL] rocblas-bench exited {completed.returncode} without a rocblas-Gflops/us row: {text[-400:]}")
    if norm_check:
        cpu_gflops = number(values.get("CPU-Gflops", ""))
        norm_error = number(values.get("norm_error_1", values.get("norm_error", "")))
        if cpu_gflops is None or norm_error is None:
            raise SystemExit("[FAIL] rocblas-bench -v 1 printed no CPU-Gflops/norm_error_1 columns")
    else:
        cpu_gflops = norm_error = NA_NO_NORM_CHECK
    seconds = gemm_us / 1e6
    flops = 2.0 * m * n * k * batch_count
    bytes_moved = (m * k + k * n + m * n) * element_bytes(dtype) * batch_count
    achieved_tflops = (flops / seconds) / 1e12 if seconds > 0 else 0.0
    traffic = (bytes_moved / seconds) / 1e9 if seconds > 0 else 0.0

    row = {
        "status": "ok", "function": function, "dtype": dtype,
        "transposeA": trans_a, "transposeB": trans_b, "M": m, "N": n, "K": k,
        "lda": lda, "ldb": ldb, "ldc": ldc, "batch_count": batch_count,
        "cold_iters": cold_iters, "hot_iters": hot_iters,
        "rocblas_gflops": gflops, "rocblas_gemm_us": gemm_us,
        "cpu_gflops": cpu_gflops, "norm_error_1": norm_error,
        "achieved_compute_tflops": achieved_tflops,
        "kernel_time_msec": gemm_us / 1000.0,
        "minimum_operand_traffic_gb_s": traffic,
        "relative_l1_checked_columns": norm_error,
        "error_message": "",
    }
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    # One rocblas-bench run already averages hot_iters calls: one sample row.
    writer.writerow({"sample_index": 0, **row})
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
